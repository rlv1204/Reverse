using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace EdgeControl.Windows.Native;

[StructLayout(LayoutKind.Sequential)]
internal struct SpDevinfoData
{
    public uint CbSize;
    public Guid ClassGuid;
    public uint DevInst;
    public IntPtr Reserved;

    public static SpDevinfoData Create() => new() { CbSize = (uint)Marshal.SizeOf<SpDevinfoData>() };
}

[StructLayout(LayoutKind.Sequential)]
internal struct SpDeviceInterfaceData
{
    public uint CbSize;
    public Guid InterfaceClassGuid;
    public uint Flags;
    public IntPtr Reserved;

    public static SpDeviceInterfaceData Create() => new() { CbSize = (uint)Marshal.SizeOf<SpDeviceInterfaceData>() };
}

[StructLayout(LayoutKind.Sequential)]
internal struct SpPropChangeParams
{
    public uint HeaderCbSize;
    public uint InstallFunction;
    public uint StateChange;
    public uint Scope;
    public uint HwProfile;
}

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
internal struct SpDevinstallParams
{
    public uint CbSize;
    public uint Flags;
    public uint FlagsEx;
    public IntPtr HwndParent;
    public IntPtr InstallMsgHandler;
    public IntPtr InstallMsgHandlerContext;
    public IntPtr FileQueue;
    public UIntPtr ClassInstallReserved;
    public uint Reserved;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
    public string DriverPath;
}

[StructLayout(LayoutKind.Sequential)]
internal struct HiddAttributes
{
    public uint Size;
    public ushort VendorId;
    public ushort ProductId;
    public ushort VersionNumber;
}

[StructLayout(LayoutKind.Sequential)]
internal struct HidpCaps
{
    public ushort Usage;
    public ushort UsagePage;
    public ushort InputReportByteLength;
    public ushort OutputReportByteLength;
    public ushort FeatureReportByteLength;

    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 17)]
    public ushort[] Reserved;

    public ushort NumberLinkCollectionNodes;
    public ushort NumberInputButtonCaps;
    public ushort NumberInputValueCaps;
    public ushort NumberInputDataIndices;
    public ushort NumberOutputButtonCaps;
    public ushort NumberOutputValueCaps;
    public ushort NumberOutputDataIndices;
    public ushort NumberFeatureButtonCaps;
    public ushort NumberFeatureValueCaps;
    public ushort NumberFeatureDataIndices;
}

internal static class NativeMethods
{
    public const uint DigcfPresent = 0x2;
    public const uint DigcfAllClasses = 0x4;
    public const uint DigcfDeviceInterface = 0x10;

    public const uint SpdrpDeviceDesc = 0x0;
    public const uint SpdrpService = 0x4;
    public const uint SpdrpDriver = 0x9;
    public const uint SpdrpFriendlyName = 0xC;
    public const uint SpdrpLowerFilters = 0x12;

    public const uint DicsFlagGlobal = 0x1;
    public const uint DicsFlagConfigSpecific = 0x2;
    public const uint DicsPropChange = 0x3;
    public const uint DiregDrv = 0x2;
    public const uint DifPropertyChange = 0x12;
    public const uint DiNeedRestart = 0x80;
    public const uint DiNeedReboot = 0x100;

    public const int KeyQueryValue = 0x0001;
    public const int KeySetValue = 0x0002;

    public const uint RegMultiSz = 7;

    public const uint DnStarted = 0x8;
    public const uint DnHasProblem = 0x400;
    public const uint CrSuccess = 0;

    public const uint GenericRead = 0x80000000;
    public const uint GenericWrite = 0x40000000;
    public const uint FileShareRead = 0x1;
    public const uint FileShareWrite = 0x2;
    public const uint OpenExisting = 3;
    public const uint FileFlagOverlapped = 0x40000000;

    public const uint IoctlUsbGetNodeInformation = 0x220408;
    public const uint IoctlUsbGetNodeConnectionDriverkeyName = 0x220420;
    public const uint IoctlUsbGetNodeConnectionInformationEx = 0x220448;

    public static readonly IntPtr InvalidHandle = new(-1);
    public static readonly Guid GuidDevinterfaceUsbHub = new("f18a0e88-c30c-11d0-8815-00a0c906bed8");
    public static readonly Guid GuidDevinterfaceHid = new("4d1e55b2-f16f-11cf-88cb-001111000030");

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr SetupDiGetClassDevsW(IntPtr classGuid, string? enumerator, IntPtr hwndParent, uint flags);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr SetupDiGetClassDevsW(ref Guid classGuid, string? enumerator, IntPtr hwndParent, uint flags);

    [DllImport("setupapi.dll", SetLastError = true)]
    public static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr classGuid, IntPtr hwndParent);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiOpenDeviceInfoW(IntPtr set, string instanceId, IntPtr hwndParent, uint flags, ref SpDevinfoData data);

    [DllImport("setupapi.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);

    [DllImport("setupapi.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiEnumDeviceInfo(IntPtr set, uint index, ref SpDevinfoData data);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiGetDeviceInstanceIdW(IntPtr set, ref SpDevinfoData data, char[] buffer, int bufferSize, out int requiredSize);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiGetDeviceRegistryPropertyW(IntPtr set, ref SpDevinfoData data, uint property, out uint regType, byte[]? buffer, uint bufferSize, out uint requiredSize);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiSetDeviceRegistryPropertyW(IntPtr set, ref SpDevinfoData data, uint property, byte[]? buffer, uint bufferSize);

    [DllImport("setupapi.dll", SetLastError = true)]
    public static extern IntPtr SetupDiOpenDevRegKey(IntPtr set, ref SpDevinfoData data, uint scope, uint hwProfile, uint keyType, int samDesired);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiSetClassInstallParamsW(IntPtr set, ref SpDevinfoData data, ref SpPropChangeParams parameters, int size);

    [DllImport("setupapi.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiCallClassInstaller(uint installFunction, IntPtr set, ref SpDevinfoData data);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiGetDeviceInstallParamsW(IntPtr set, ref SpDevinfoData data, ref SpDevinstallParams parameters);

    [DllImport("setupapi.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiEnumDeviceInterfaces(IntPtr set, IntPtr devInfo, ref Guid interfaceGuid, uint index, ref SpDeviceInterfaceData data);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetupDiGetDeviceInterfaceDetailW(IntPtr set, ref SpDeviceInterfaceData data, IntPtr detail, uint detailSize, out uint requiredSize, IntPtr devInfo);

    [DllImport("cfgmgr32.dll")]
    public static extern uint CM_Locate_DevNodeW(out uint devInst, [MarshalAs(UnmanagedType.LPWStr)] string deviceId, uint flags);

    [DllImport("cfgmgr32.dll")]
    public static extern uint CM_Get_Parent(out uint parent, uint devInst, uint flags);

    [DllImport("cfgmgr32.dll")]
    public static extern uint CM_Get_Child(out uint child, uint devInst, uint flags);

    [DllImport("cfgmgr32.dll")]
    public static extern uint CM_Get_Sibling(out uint sibling, uint devInst, uint flags);

    [DllImport("cfgmgr32.dll", CharSet = CharSet.Unicode)]
    public static extern uint CM_Get_Device_IDW(uint devInst, char[] buffer, int bufferLen, uint flags);

    [DllImport("cfgmgr32.dll")]
    public static extern uint CM_Get_DevNode_Status(out uint status, out uint problem, uint devInst, uint flags);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool DeviceIoControl(SafeFileHandle device, uint code, byte[] inBuffer, int inSize, byte[] outBuffer, int outSize, out int returned, IntPtr overlapped);

    [DllImport("hid.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool HidD_GetAttributes(SafeFileHandle device, ref HiddAttributes attributes);

    [DllImport("hid.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool HidD_GetFeature(SafeFileHandle device, byte[] buffer, int length);

    [DllImport("hid.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool HidD_SetNumInputBuffers(SafeFileHandle device, int count);

    [DllImport("hid.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool HidD_GetPreparsedData(SafeFileHandle device, out IntPtr preparsed);

    [DllImport("hid.dll")]
    [return: MarshalAs(UnmanagedType.U1)]
    public static extern bool HidD_FreePreparsedData(IntPtr preparsed);

    [DllImport("hid.dll")]
    public static extern int HidP_GetCaps(IntPtr preparsed, ref HidpCaps caps);
}
