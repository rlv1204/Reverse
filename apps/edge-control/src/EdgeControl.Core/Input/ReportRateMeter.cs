namespace EdgeControl.Core.Input;

/// <summary>
/// Measures the delivered input report rate from report arrival times.
/// The controller's 8-bit sequence counter detects reports the host dropped,
/// so a buffered burst still counts every report the device sent.
/// </summary>
public sealed class ReportRateMeter
{
    private readonly TimeSpan _window;
    private readonly Queue<(TimeSpan At, int Count)> _samples = new();
    private int _total;
    private byte? _lastSequence;

    public ReportRateMeter(TimeSpan window)
    {
        if (window <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(window));
        }

        _window = window;
    }

    public long DroppedReports { get; private set; }

    /// <summary>Records one received report.</summary>
    public void Record(TimeSpan at, byte sequence)
    {
        var count = 1;
        if (_lastSequence is { } last)
        {
            var gap = (byte)(sequence - last);
            if (gap > 1)
            {
                DroppedReports += gap - 1;
                count = gap;
            }
            else if (gap == 0)
            {
                // Same counter: some firmware repeats it; count the report as received.
                count = 1;
            }
        }

        _lastSequence = sequence;
        _samples.Enqueue((at, count));
        _total += count;
        Trim(at);
    }

    /// <summary>Reports per second over the window ending at <paramref name="now"/>.</summary>
    public double RateHz(TimeSpan now)
    {
        Trim(now);
        if (_samples.Count < 2)
        {
            return 0;
        }

        var span = now - _samples.Peek().At;
        return span <= TimeSpan.Zero ? 0 : (_total - _samples.Peek().Count) / span.TotalSeconds;
    }

    public void Reset()
    {
        _samples.Clear();
        _total = 0;
        _lastSequence = null;
        DroppedReports = 0;
    }

    private void Trim(TimeSpan now)
    {
        while (_samples.Count > 0 && now - _samples.Peek().At > _window)
        {
            _total -= _samples.Dequeue().Count;
        }
    }
}
