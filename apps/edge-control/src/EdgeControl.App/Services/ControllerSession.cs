using EdgeControl.Core.Devices;
using EdgeControl.Core.Input;
using EdgeControl.Windows;

namespace EdgeControl.App.Services;

public enum ConnectionKind
{
    None,
    Usb,
    Bluetooth,
}

/// <summary>
/// Owns the single read-only HID connection. Reports arrive on a worker
/// thread at up to 8000 Hz; the UI samples <see cref="Latest"/> on a timer
/// instead of being notified per report.
/// </summary>
public sealed class ControllerSession : IDisposable
{
    private readonly object _gate = new();
    private readonly ReportRateMeter _meter = new(TimeSpan.FromSeconds(1));
    private readonly System.Diagnostics.Stopwatch _clock = System.Diagnostics.Stopwatch.StartNew();
    private EdgeHidConnection? _connection;
    private EdgeInputReport? _latest;
    private TimeSpan _offset;
    private bool _paused;

    public ConnectionKind Kind { get; private set; }
    public FirmwareInfo? Firmware { get; private set; }
    public string? LastError { get; private set; }

    public EdgeInputReport? Latest
    {
        get { lock (_gate) return _latest; }
    }

    public double RateHz
    {
        get { lock (_gate) return _meter.RateHz(_clock.Elapsed); }
    }

    public long DroppedReports
    {
        get { lock (_gate) return _meter.DroppedReports; }
    }

    /// <summary>Connects when idle; call periodically. Bluetooth is detected but not read.</summary>
    public void EnsureConnected()
    {
        if (_paused || _connection is not null)
        {
            return;
        }

        IReadOnlyList<EdgeHidPath> paths;
        try
        {
            paths = EdgeHidConnection.FindPaths();
        }
        catch (Exception error)
        {
            LastError = error.Message;
            return;
        }

        var usb = paths.FirstOrDefault(p => p.Transport == EdgeTransport.Usb);
        if (usb is null)
        {
            Kind = paths.Any(p => p.Transport == EdgeTransport.Bluetooth) ? ConnectionKind.Bluetooth : ConnectionKind.None;
            return;
        }

        var connection = EdgeHidConnection.TryOpen(usb);
        if (connection is null)
        {
            LastError = "Não foi possível abrir o controle. Outro programa pode estar usando-o em modo exclusivo.";
            Kind = ConnectionKind.None;
            return;
        }

        LastError = null;
        Firmware = connection.ReadFirmwareInfo();
        lock (_gate)
        {
            _meter.Reset();
            _latest = null;
            _offset = _clock.Elapsed;
        }

        connection.ReportReceived += OnReport;
        connection.Disconnected += OnDisconnected;
        _connection = connection;
        Kind = ConnectionKind.Usb;
        connection.Start();
    }

    /// <summary>Releases the device so Windows can restart it (the setup warns an open handle blocks restart).</summary>
    public void Pause()
    {
        _paused = true;
        Close();
    }

    public void Resume() => _paused = false;

    private void OnReport(EdgeInputReport report, TimeSpan at)
    {
        lock (_gate)
        {
            _latest = report;
            _meter.Record(_offset + at, report.Sequence);
        }
    }

    private void OnDisconnected(Exception error)
    {
        LastError = error.Message;

        // Raised from the reader task; closing waits for that task, so close elsewhere.
        _ = Task.Run(Close);
    }

    private void Close()
    {
        var connection = Interlocked.Exchange(ref _connection, null);
        if (connection is not null)
        {
            connection.ReportReceived -= OnReport;
            connection.Disconnected -= OnDisconnected;
            connection.Dispose();
        }

        Kind = ConnectionKind.None;
        Firmware = null;
        lock (_gate)
        {
            _latest = null;
            _meter.Reset();
        }
    }

    public void Dispose() => Close();
}
