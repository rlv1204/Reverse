using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;
using static EdgeControl.Windows.Native.NativeMethods;

namespace EdgeControl.Windows.Native;

/// <summary>Owns one SetupAPI device information set.</summary>
internal sealed class DeviceInfoSet : IDisposable
{
    private IntPtr _handle;

    private DeviceInfoSet(IntPtr handle)
    {
        if (handle == InvalidHandle || handle == IntPtr.Zero)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }

        _handle = handle;
    }

    public IntPtr Handle => _handle;

    /// <summary>All present devices of the USB enumerator.</summary>
    public static DeviceInfoSet PresentUsbDevices() =>
        new(SetupDiGetClassDevsW(IntPtr.Zero, "USB", IntPtr.Zero, DigcfPresent | DigcfAllClasses));

    public static DeviceInfoSet PresentInterfaces(Guid interfaceGuid, string? deviceInstanceId = null) =>
        new(SetupDiGetClassDevsW(ref interfaceGuid, deviceInstanceId, IntPtr.Zero, DigcfPresent | DigcfDeviceInterface));

    /// <summary>Opens exactly one device by instance id, as the hidusbf setup does.</summary>
    public static (DeviceInfoSet Set, SpDevinfoData Data) Open(string instanceId)
    {
        var set = new DeviceInfoSet(SetupDiCreateDeviceInfoList(IntPtr.Zero, IntPtr.Zero));
        var data = SpDevinfoData.Create();
        if (!SetupDiOpenDeviceInfoW(set._handle, instanceId, IntPtr.Zero, 0, ref data))
        {
            var error = Marshal.GetLastWin32Error();
            set.Dispose();
            throw new Win32Exception(error, $"Dispositivo não encontrado: {instanceId}");
        }

        return (set, data);
    }

    public IEnumerable<SpDevinfoData> Devices()
    {
        for (uint i = 0; ; i++)
        {
            var data = SpDevinfoData.Create();
            if (!SetupDiEnumDeviceInfo(_handle, i, ref data))
            {
                yield break;
            }

            yield return data;
        }
    }

    public IEnumerable<string> InterfacePaths(Guid interfaceGuid)
    {
        for (uint i = 0; ; i++)
        {
            var data = SpDeviceInterfaceData.Create();
            if (!SetupDiEnumDeviceInterfaces(_handle, IntPtr.Zero, ref interfaceGuid, i, ref data))
            {
                yield break;
            }

            SetupDiGetDeviceInterfaceDetailW(_handle, ref data, IntPtr.Zero, 0, out var required, IntPtr.Zero);
            if (required == 0)
            {
                continue;
            }

            var buffer = Marshal.AllocHGlobal((int)required);
            try
            {
                // SP_DEVICE_INTERFACE_DETAIL_DATA_W.cbSize: 8 on x64, 6 on x86.
                Marshal.WriteInt32(buffer, IntPtr.Size == 8 ? 8 : 6);
                if (SetupDiGetDeviceInterfaceDetailW(_handle, ref data, buffer, required, out _, IntPtr.Zero))
                {
                    var path = Marshal.PtrToStringUni(buffer + 4);
                    if (!string.IsNullOrEmpty(path))
                    {
                        yield return path;
                    }
                }
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
    }

    public string InstanceId(ref SpDevinfoData data)
    {
        var buffer = new char[512];
        if (!SetupDiGetDeviceInstanceIdW(_handle, ref data, buffer, buffer.Length, out var required))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }

        return new string(buffer, 0, Math.Max(0, required - 1));
    }

    public byte[]? Property(ref SpDevinfoData data, uint property)
    {
        SetupDiGetDeviceRegistryPropertyW(_handle, ref data, property, out _, null, 0, out var required);
        if (required == 0)
        {
            return null;
        }

        var buffer = new byte[required];
        return SetupDiGetDeviceRegistryPropertyW(_handle, ref data, property, out _, buffer, required, out _) ? buffer : null;
    }

    public string? StringProperty(ref SpDevinfoData data, uint property) =>
        Property(ref data, property) is { } bytes ? Encoding.Unicode.GetString(bytes).TrimEnd('\0') : null;

    public IReadOnlyList<string> MultiStringProperty(ref SpDevinfoData data, uint property) =>
        Property(ref data, property) is { } bytes ? MultiSz.Decode(bytes) : [];

    public void SetMultiStringProperty(ref SpDevinfoData data, uint property, IReadOnlyList<string> values)
    {
        // An empty list removes the property, like RegDeleteValue in the setup.
        var bytes = values.Count == 0 ? null : MultiSz.Encode(values);
        if (!SetupDiSetDeviceRegistryPropertyW(_handle, ref data, property, bytes, (uint)(bytes?.Length ?? 0)))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Falha ao gravar LowerFilters");
        }
    }

    /// <summary>Opens the device driver key (DIREG_DRV), where hidusbf reads "bInterval".</summary>
    public RegistryKey OpenDriverKey(ref SpDevinfoData data, bool writable)
    {
        var access = KeyQueryValue | (writable ? KeySetValue : 0);
        var key = SetupDiOpenDevRegKey(_handle, ref data, DicsFlagGlobal, 0, DiregDrv, access);
        if (key == InvalidHandle)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Falha ao abrir a chave do driver do dispositivo");
        }

        return RegistryKey.FromHandle(new SafeRegistryHandle(key, ownsHandle: true));
    }

    /// <summary>DIF_PROPERTYCHANGE / DICS_PROPCHANGE, the setup's "Restart" button.</summary>
    /// <returns>True when Windows asks for a reboot to finish.</returns>
    public bool RestartDevice(ref SpDevinfoData data)
    {
        var parameters = new SpPropChangeParams
        {
            HeaderCbSize = 8,
            InstallFunction = DifPropertyChange,
            StateChange = DicsPropChange,
            Scope = DicsFlagConfigSpecific,
            HwProfile = 0,
        };

        if (!SetupDiSetClassInstallParamsW(_handle, ref data, ref parameters, Marshal.SizeOf<SpPropChangeParams>())
            || !SetupDiCallClassInstaller(DifPropertyChange, _handle, ref data))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Falha ao reiniciar o controle");
        }

        var install = new SpDevinstallParams { CbSize = (uint)Marshal.SizeOf<SpDevinstallParams>(), DriverPath = string.Empty };
        return SetupDiGetDeviceInstallParamsW(_handle, ref data, ref install)
            && (install.Flags & (DiNeedRestart | DiNeedReboot)) != 0;
    }

    public void Dispose()
    {
        if (_handle != IntPtr.Zero)
        {
            SetupDiDestroyDeviceInfoList(_handle);
            _handle = IntPtr.Zero;
        }
    }
}

internal static class MultiSz
{
    public static IReadOnlyList<string> Decode(byte[] bytes) =>
        Encoding.Unicode.GetString(bytes).Split('\0', StringSplitOptions.RemoveEmptyEntries);

    public static byte[] Encode(IReadOnlyList<string> values) =>
        Encoding.Unicode.GetBytes(string.Concat(values.Select(v => v + "\0")) + "\0");
}

internal static class ConfigManager
{
    public static uint? Locate(string instanceId) =>
        CM_Locate_DevNodeW(out var devInst, instanceId, 0) == CrSuccess ? devInst : null;

    public static uint? Parent(uint devInst) => CM_Get_Parent(out var p, devInst, 0) == CrSuccess ? p : null;

    public static string? InstanceId(uint devInst)
    {
        var buffer = new char[512];
        return CM_Get_Device_IDW(devInst, buffer, buffer.Length, 0) == CrSuccess
            ? new string(buffer).TrimEnd('\0')
            : null;
    }

    public static (uint Status, uint Problem)? Status(uint devInst) =>
        CM_Get_DevNode_Status(out var status, out var problem, devInst, 0) == CrSuccess ? (status, problem) : null;

    public static IReadOnlyList<uint> Children(uint devInst)
    {
        var result = new List<uint>();
        if (CM_Get_Child(out var child, devInst, 0) != CrSuccess)
        {
            return result;
        }

        result.Add(child);
        while (CM_Get_Sibling(out var next, child, 0) == CrSuccess)
        {
            result.Add(next);
            child = next;
        }

        return result;
    }
}
