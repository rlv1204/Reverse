using System.Text;
using EdgeControl.Core.Overclock;
using EdgeControl.Windows.Native;
using static EdgeControl.Windows.Native.NativeMethods;

namespace EdgeControl.Windows;

/// <summary>An open pipe as the hub reports it (USB_PIPE_INFO).</summary>
public sealed record UsbPipe(byte EndpointAddress, byte Attributes, ushort MaxPacketSize, byte BInterval)
{
    public bool IsInterrupt => (Attributes & 0x03) == 0x03;
    public bool IsIn => (EndpointAddress & 0x80) != 0;
}

public sealed record UsbPortInfo(int Port, UsbBusSpeed Speed, IReadOnlyList<UsbPipe> Pipes);

/// <summary>
/// Reads speed and live pipe intervals from the parent hub, using the same
/// IOCTLs as the hidusbf setup: node information for the port count, the
/// per-port driver key name to find our device, then connection information.
/// </summary>
internal static class UsbHubQuery
{
    // USB_NODE_CONNECTION_INFORMATION_EX is packed to 1 byte (usbioctl.h).
    private const int ConnectionHeaderSize = 35;
    private const int PipeInfoSize = 11;
    private const int MaxPipes = 32;

    public static UsbPortInfo? Query(string hubInstanceId, string deviceDriverKey)
    {
        using var hubs = DeviceInfoSet.PresentInterfaces(GuidDevinterfaceUsbHub, hubInstanceId);
        var hubPath = hubs.InterfacePaths(GuidDevinterfaceUsbHub).FirstOrDefault();
        if (hubPath is null)
        {
            return null;
        }

        using var hub = CreateFileW(hubPath, GenericWrite, FileShareWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
        if (hub.IsInvalid)
        {
            return null;
        }

        var node = new byte[76];
        if (!DeviceIoControl(hub, IoctlUsbGetNodeInformation, node, node.Length, node, node.Length, out _, IntPtr.Zero))
        {
            return null;
        }

        // NodeType (ULONG) then USB_HUB_DESCRIPTOR: bDescriptorLength, bDescriptorType, bNumberOfPorts.
        int ports = node[6];
        for (var port = 1; port <= ports; port++)
        {
            if (!string.Equals(DriverKeyName(hub, port), deviceDriverKey, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            return ConnectionInfo(hub, port);
        }

        return null;
    }

    private static string? DriverKeyName(Microsoft.Win32.SafeHandles.SafeFileHandle hub, int port)
    {
        var probe = new byte[12];
        BitConverter.GetBytes(port).CopyTo(probe, 0);
        if (!DeviceIoControl(hub, IoctlUsbGetNodeConnectionDriverkeyName, probe, probe.Length, probe, probe.Length, out _, IntPtr.Zero))
        {
            return null;
        }

        var actual = BitConverter.ToInt32(probe, 4);
        if (actual <= 8 || actual > 4096)
        {
            return null;
        }

        var buffer = new byte[actual];
        BitConverter.GetBytes(port).CopyTo(buffer, 0);
        if (!DeviceIoControl(hub, IoctlUsbGetNodeConnectionDriverkeyName, buffer, buffer.Length, buffer, buffer.Length, out _, IntPtr.Zero))
        {
            return null;
        }

        return Encoding.Unicode.GetString(buffer, 8, actual - 8).TrimEnd('\0');
    }

    private static UsbPortInfo? ConnectionInfo(Microsoft.Win32.SafeHandles.SafeFileHandle hub, int port)
    {
        var buffer = new byte[ConnectionHeaderSize + MaxPipes * PipeInfoSize];
        BitConverter.GetBytes(port).CopyTo(buffer, 0);
        if (!DeviceIoControl(hub, IoctlUsbGetNodeConnectionInformationEx, buffer, buffer.Length, buffer, buffer.Length, out var returned, IntPtr.Zero))
        {
            return null;
        }

        var speed = buffer[23] switch
        {
            0 => UsbBusSpeed.Low,
            1 => UsbBusSpeed.Full,
            2 => UsbBusSpeed.High,
            3 => UsbBusSpeed.Super,
            _ => UsbBusSpeed.Unknown,
        };

        var pipeCount = Math.Min(BitConverter.ToInt32(buffer, 27), MaxPipes);
        var pipes = new List<UsbPipe>(pipeCount);
        for (var i = 0; i < pipeCount; i++)
        {
            var offset = ConnectionHeaderSize + i * PipeInfoSize;
            if (offset + PipeInfoSize > returned)
            {
                break;
            }

            // USB_ENDPOINT_DESCRIPTOR: bLength, bDescriptorType, bEndpointAddress, bmAttributes, wMaxPacketSize, bInterval.
            pipes.Add(new UsbPipe(buffer[offset + 2], buffer[offset + 3], BitConverter.ToUInt16(buffer, offset + 4), buffer[offset + 6]));
        }

        return new UsbPortInfo(port, speed, pipes);
    }
}
