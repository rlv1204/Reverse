using EdgeControl.Core.Devices;
using EdgeControl.Core.Overclock;
using EdgeControl.Windows.Native;
using static EdgeControl.Windows.Native.NativeMethods;

namespace EdgeControl.Windows;

public sealed record UsbInterfaceNode(string InstanceId, IReadOnlyList<string> LowerFilters);

/// <summary>
/// The hub-attached USB node of a DualSense Edge plus everything the
/// overclock section needs to know about it. All fields are observed values;
/// null means Windows did not report the value.
/// </summary>
public sealed record EdgeUsbDevice(
    string InstanceId,
    string Name,
    string? DriverKey,
    string? HubInstanceId,
    string? ControllerInstanceId,
    string? ControllerService,
    IReadOnlyList<string> LowerFilters,
    int? StoredBInterval,
    int ProblemCode,
    bool Started,
    UsbPortInfo? Port,
    IReadOnlyList<UsbInterfaceNode> Interfaces)
{
    public UsbBusSpeed Speed => Port?.Speed ?? UsbBusSpeed.Unknown;

    /// <summary>Interrupt IN pipes; the Edge reports input on one of them.</summary>
    public IEnumerable<UsbPipe> InterruptInPipes => Port?.Pipes.Where(p => p.IsInterrupt && p.IsIn) ?? [];

    public OverclockFacts ToFacts(HidUsbfStatus driver) => new()
    {
        InstanceId = InstanceId,
        BusSpeed = Speed,
        LowerFilters = LowerFilters,
        StoredBInterval = StoredBInterval,
        ProblemCode = ProblemCode,
        Service = driver.State,
        ControllerService = ControllerService,
    };

    public string Diagnostic(HidUsbfStatus driver)
    {
        var lines = new List<string>
        {
            $"Dispositivo: {Name}",
            $"  InstanceId: {InstanceId}",
            $"  DriverKey: {DriverKey ?? "?"}",
            $"  LowerFilters: {string.Join(", ", LowerFilters)}",
            $"  bInterval (registro): {StoredBInterval?.ToString() ?? "ausente"}",
            $"  Problema: {ProblemCode}  Iniciado: {Started}",
            $"  Velocidade: {Speed}  Porta: {Port?.Port.ToString() ?? "?"}",
        };
        foreach (var pipe in Port?.Pipes ?? [])
        {
            lines.Add($"  Pipe 0x{pipe.EndpointAddress:X2} attr=0x{pipe.Attributes:X2} max={pipe.MaxPacketSize} bInterval={pipe.BInterval}");
        }

        foreach (var child in Interfaces)
        {
            lines.Add($"  Interface: {child.InstanceId}  LowerFilters: {string.Join(", ", child.LowerFilters)}");
        }

        lines.Add($"Hub: {HubInstanceId ?? "?"}");
        lines.Add($"Controladora: {ControllerInstanceId ?? "?"} (serviço {ControllerService ?? "?"})");
        lines.Add($"hidusbf: {driver.State} versão {driver.FileVersion ?? "?"}  Integridade de Memória: {driver.MemoryIntegrity}  TestSigning: {driver.TestSigning}");
        lines.Add($"SO: {Environment.OSVersion}  64 bits: {Environment.Is64BitOperatingSystem}");
        return string.Join(Environment.NewLine, lines);
    }
}

public static class EdgeUsbDevices
{
    public static IReadOnlyList<EdgeUsbDevice> FindPresent()
    {
        var result = new List<EdgeUsbDevice>();
        using var set = DeviceInfoSet.PresentUsbDevices();
        foreach (var item in set.Devices())
        {
            var data = item;
            var instanceId = set.InstanceId(ref data);
            if (!EdgeIdentity.IsUsbDeviceNode(instanceId))
            {
                continue;
            }

            result.Add(Read(set, ref data, instanceId));
        }

        return result;
    }

    /// <summary>Re-reads one device by instance id; null when it is gone.</summary>
    public static EdgeUsbDevice? Refresh(string instanceId)
    {
        if (ConfigManager.Locate(instanceId) is null)
        {
            return null;
        }

        try
        {
            var (set, data) = DeviceInfoSet.Open(instanceId);
            using (set)
            {
                return Read(set, ref data, instanceId);
            }
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return null;
        }
    }

    private static EdgeUsbDevice Read(DeviceInfoSet set, ref SpDevinfoData data, string instanceId)
    {
        var name = set.StringProperty(ref data, SpdrpFriendlyName)
            ?? set.StringProperty(ref data, SpdrpDeviceDesc)
            ?? "DualSense Edge";
        var driverKey = set.StringProperty(ref data, SpdrpDriver);
        var filters = set.MultiStringProperty(ref data, SpdrpLowerFilters);

        int? stored = null;
        try
        {
            using var key = set.OpenDriverKey(ref data, writable: false);
            if (key.GetValue("bInterval") is int value)
            {
                stored = value;
            }
        }
        catch (System.ComponentModel.Win32Exception)
        {
            // No driver key yet: the value is absent.
        }

        var status = ConfigManager.Status(data.DevInst);
        var problem = status is { } s && (s.Status & DnHasProblem) != 0 ? (int)s.Problem : 0;
        var started = status is { } st && (st.Status & DnStarted) != 0;

        var hubDevInst = ConfigManager.Parent(data.DevInst);
        var hubId = hubDevInst is { } h ? ConfigManager.InstanceId(h) : null;
        var (controllerId, controllerService) = FindController(hubDevInst);

        UsbPortInfo? port = null;
        if (hubId is not null && driverKey is not null)
        {
            port = UsbHubQuery.Query(hubId, driverKey);
        }

        var interfaces = new List<UsbInterfaceNode>();
        foreach (var child in ConfigManager.Children(data.DevInst))
        {
            if (ConfigManager.InstanceId(child) is { } childId && EdgeIdentity.IsUsbInterfaceNode(childId))
            {
                interfaces.Add(new UsbInterfaceNode(childId, ReadFilters(childId)));
            }
        }

        return new EdgeUsbDevice(instanceId, name, driverKey, hubId, controllerId, controllerService, filters, stored, problem, started, port, interfaces);
    }

    /// <summary>Walks up from the hub to the first non-USB ancestor: the host controller.</summary>
    private static (string? InstanceId, string? Service) FindController(uint? start)
    {
        var current = start;
        for (var depth = 0; current is { } devInst && depth < 16; depth++)
        {
            var id = ConfigManager.InstanceId(devInst);
            if (id is null)
            {
                break;
            }

            if (!id.StartsWith(@"USB\", StringComparison.OrdinalIgnoreCase))
            {
                return (id, ServiceOf(id));
            }

            current = ConfigManager.Parent(devInst);
        }

        return (null, null);
    }

    private static string? ServiceOf(string instanceId)
    {
        try
        {
            var (set, data) = DeviceInfoSet.Open(instanceId);
            using (set)
            {
                return set.StringProperty(ref data, SpdrpService);
            }
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return null;
        }
    }

    private static IReadOnlyList<string> ReadFilters(string instanceId)
    {
        try
        {
            var (set, data) = DeviceInfoSet.Open(instanceId);
            using (set)
            {
                return set.MultiStringProperty(ref data, SpdrpLowerFilters);
            }
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return [];
        }
    }
}
