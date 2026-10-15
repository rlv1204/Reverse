using System.Diagnostics;
using EdgeControl.Core.Overclock;
using Microsoft.Win32;

namespace EdgeControl.Windows;

public enum ToggleState
{
    Unknown,
    Off,
    On,
}

/// <summary>
/// Read-only view of the hidusbf installation. This app never installs,
/// starts, or modifies the driver service itself.
/// </summary>
public sealed record HidUsbfStatus(
    HidUsbfServiceState State,
    string? DriverPath,
    string? FileVersion,
    ToggleState MemoryIntegrity,
    ToggleState TestSigning)
{
    private const string ServiceKey = @"SYSTEM\CurrentControlSet\Services\hidusbf";

    public static HidUsbfStatus Read()
    {
        var memoryIntegrity = ReadMemoryIntegrity();
        var testSigning = ReadTestSigning();

        using var service = Registry.LocalMachine.OpenSubKey(ServiceKey);
        if (service is null)
        {
            return new HidUsbfStatus(HidUsbfServiceState.NotInstalled, null, null, memoryIntegrity, testSigning);
        }

        var path = ResolveImagePath(service.GetValue("ImagePath") as string);
        var version = File.Exists(path) ? FileVersionInfo.GetVersionInfo(path).FileVersion : null;
        var state = service.GetValue("Start") is int start && start == 4
            ? HidUsbfServiceState.Disabled
            : File.Exists(path) ? HidUsbfServiceState.Installed : HidUsbfServiceState.DriverFileMissing;

        return new HidUsbfStatus(state, path, version, memoryIntegrity, testSigning);
    }

    private static string ResolveImagePath(string? imagePath)
    {
        var windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        if (string.IsNullOrWhiteSpace(imagePath))
        {
            return Path.Combine(windows, "System32", "drivers", "hidusbf.sys");
        }

        var path = imagePath.Trim('"');
        if (path.StartsWith(@"\SystemRoot\", StringComparison.OrdinalIgnoreCase))
        {
            return Path.Combine(windows, path[@"\SystemRoot\".Length..]);
        }

        if (path.StartsWith(@"\??\", StringComparison.Ordinal))
        {
            return path[4..];
        }

        return Path.IsPathRooted(path) ? path : Path.Combine(windows, path);
    }

    private static ToggleState ReadMemoryIntegrity()
    {
        using var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity");
        return key?.GetValue("Enabled") switch
        {
            1 => ToggleState.On,
            0 => ToggleState.Off,
            _ => key is null ? ToggleState.Off : ToggleState.Unknown,
        };
    }

    private static ToggleState ReadTestSigning()
    {
        using var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Control");
        return key?.GetValue("SystemStartOptions") is string options
            ? options.Contains("TESTSIGNING", StringComparison.OrdinalIgnoreCase) ? ToggleState.On : ToggleState.Off
            : ToggleState.Unknown;
    }
}
