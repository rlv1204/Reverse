namespace EdgeControl.Core.Devices;

/// <summary>
/// USB identity of the DualSense Edge (CFI-ZCP1). The app only ever writes
/// configuration for a device node that matches this identity.
/// </summary>
public static class EdgeIdentity
{
    public const ushort VendorId = 0x054C;
    public const ushort ProductId = 0x0DF2;

    /// <summary>Prefix of the USB device node attached to the hub port (composite parent).</summary>
    public const string UsbInstancePrefix = @"USB\VID_054C&PID_0DF2";

    /// <summary>
    /// True for the hub-attached device node (<c>USB\VID_054C&amp;PID_0DF2\serial</c>),
    /// false for interface children (<c>...&amp;MI_03\...</c>) and any other device.
    /// </summary>
    public static bool IsUsbDeviceNode(string instanceId)
    {
        if (!instanceId.StartsWith(UsbInstancePrefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        // The character right after the prefix separates the hardware id from the instance path.
        return instanceId.Length > UsbInstancePrefix.Length && instanceId[UsbInstancePrefix.Length] == '\\';
    }

    /// <summary>True for an interface child of the Edge (<c>USB\VID_054C&amp;PID_0DF2&amp;MI_xx\...</c>).</summary>
    public static bool IsUsbInterfaceNode(string instanceId) =>
        instanceId.StartsWith(UsbInstancePrefix + "&MI_", StringComparison.OrdinalIgnoreCase);

    /// <summary>
    /// HID device interface paths are lower-case and contain <c>vid_054c&amp;pid_0df2</c> over USB.
    /// Bluetooth paths use the <c>{00001124-...}_vid&amp;0002054c_pid&amp;0df2</c> form instead.
    /// </summary>
    public static EdgeTransport ClassifyHidPath(string devicePath)
    {
        var path = devicePath.ToLowerInvariant();
        if (path.Contains("vid_054c&pid_0df2"))
        {
            return EdgeTransport.Usb;
        }

        if (path.Contains("vid&0002054c_pid&0df2"))
        {
            return EdgeTransport.Bluetooth;
        }

        return EdgeTransport.NotEdge;
    }
}

public enum EdgeTransport
{
    NotEdge,
    Usb,
    Bluetooth,
}
