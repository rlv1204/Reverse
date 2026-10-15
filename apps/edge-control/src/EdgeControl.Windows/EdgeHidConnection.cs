using System.Diagnostics;
using EdgeControl.Core.Devices;
using EdgeControl.Core.Input;
using EdgeControl.Windows.Native;
using Microsoft.Win32.SafeHandles;
using static EdgeControl.Windows.Native.NativeMethods;

namespace EdgeControl.Windows;

public sealed record EdgeHidPath(string DevicePath, EdgeTransport Transport);

/// <summary>
/// Read-only HID session with the controller: input reports and GET feature
/// reports. It never sends output reports or SET feature reports, so it
/// cannot change anything stored on the controller.
/// </summary>
public sealed class EdgeHidConnection : IDisposable
{
    private readonly SafeFileHandle _handle;
    private readonly FileStream _stream;
    private readonly int _inputLength;
    private readonly CancellationTokenSource _stop = new();
    private Task? _reader;

    private EdgeHidConnection(SafeFileHandle handle, int inputLength, string path, EdgeTransport transport)
    {
        _handle = handle;
        _inputLength = inputLength;
        _stream = new FileStream(handle, FileAccess.Read, 0, isAsync: true);
        DevicePath = path;
        Transport = transport;
    }

    public string DevicePath { get; }
    public EdgeTransport Transport { get; }

    /// <summary>Raised on a worker thread for every input report.</summary>
    public event Action<EdgeInputReport, TimeSpan>? ReportReceived;

    public event Action<Exception>? Disconnected;

    public static IReadOnlyList<EdgeHidPath> FindPaths()
    {
        using var set = DeviceInfoSet.PresentInterfaces(GuidDevinterfaceHid);
        return set.InterfacePaths(GuidDevinterfaceHid)
            .Select(p => new EdgeHidPath(p, EdgeIdentity.ClassifyHidPath(p)))
            .Where(p => p.Transport != EdgeTransport.NotEdge)
            .ToArray();
    }

    public static EdgeHidConnection? TryOpen(EdgeHidPath path)
    {
        // Read/write access is needed for GET feature reports; fall back to read-only.
        var handle = CreateFileW(path.DevicePath, GenericRead | GenericWrite, FileShareRead | FileShareWrite, IntPtr.Zero, OpenExisting, FileFlagOverlapped, IntPtr.Zero);
        if (handle.IsInvalid)
        {
            handle.Dispose();
            handle = CreateFileW(path.DevicePath, GenericRead, FileShareRead | FileShareWrite, IntPtr.Zero, OpenExisting, FileFlagOverlapped, IntPtr.Zero);
        }

        if (handle.IsInvalid)
        {
            handle.Dispose();
            return null;
        }

        var attributes = new HiddAttributes { Size = (uint)System.Runtime.InteropServices.Marshal.SizeOf<HiddAttributes>() };
        if (!HidD_GetAttributes(handle, ref attributes)
            || attributes.VendorId != EdgeIdentity.VendorId
            || attributes.ProductId != EdgeIdentity.ProductId)
        {
            handle.Dispose();
            return null;
        }

        var inputLength = EdgeInputReport.UsbReportLength;
        if (HidD_GetPreparsedData(handle, out var preparsed))
        {
            var caps = new HidpCaps();
            if (HidP_GetCaps(preparsed, ref caps) >= 0 && caps.InputReportByteLength > 0)
            {
                inputLength = caps.InputReportByteLength;
            }

            HidD_FreePreparsedData(preparsed);
        }

        // A larger ring keeps reports from being dropped at 8000 Hz; host-side only.
        HidD_SetNumInputBuffers(handle, 512);
        return new EdgeHidConnection(handle, inputLength, path.DevicePath, path.Transport);
    }

    public FirmwareInfo? ReadFirmwareInfo()
    {
        var buffer = new byte[FirmwareInfo.ReportLength];
        buffer[0] = FirmwareInfo.ReportId;
        return HidD_GetFeature(_handle, buffer, buffer.Length) ? FirmwareInfo.TryParse(buffer) : null;
    }

    public void Start()
    {
        _reader ??= Task.Run(ReadLoopAsync);
    }

    private async Task ReadLoopAsync()
    {
        var clock = Stopwatch.StartNew();
        var buffer = new byte[_inputLength];
        try
        {
            while (!_stop.IsCancellationRequested)
            {
                var read = await _stream.ReadAsync(buffer, _stop.Token);
                if (read == 0)
                {
                    throw new IOException("O controle foi desconectado.");
                }

                if (EdgeInputReport.TryParseUsb(buffer.AsSpan(0, read), out var report))
                {
                    ReportReceived?.Invoke(report, clock.Elapsed);
                }
            }
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception error) when (!_stop.IsCancellationRequested)
        {
            Disconnected?.Invoke(error);
        }
    }

    public void Dispose()
    {
        _stop.Cancel();
        _stream.Dispose();
        try
        {
            _reader?.Wait(TimeSpan.FromSeconds(2));
        }
        catch (AggregateException)
        {
        }

        _handle.Dispose();
        _stop.Dispose();
    }
}
