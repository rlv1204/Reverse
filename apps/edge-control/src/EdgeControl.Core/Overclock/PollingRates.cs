namespace EdgeControl.Core.Overclock;

/// <summary>
/// USB bus speed as reported by the hub (USB_DEVICE_SPEED in usbspec.h).
/// </summary>
public enum UsbBusSpeed
{
    Low = 0,
    Full = 1,
    High = 2,
    Super = 3,
    SuperPlus = 4,
    Unknown = 255,
}

/// <summary>
/// One selectable polling rate. <see cref="RegistryBInterval"/> is the exact
/// DWORD hidusbf reads from the device driver key, or null when the value
/// must be absent (device default).
/// </summary>
public sealed record PollingRateOption(int Index, int? RegistryBInterval, int? Hz)
{
    public bool IsDefault => RegistryBInterval is null;

    public string Label => Hz is { } hz ? $"{hz} Hz" : "Padrão do controle";
}

/// <summary>
/// Rate semantics recovered from the hidusbf Setup.exe (BB build, SHA-256
/// c461d2ce...d9e314). The setup offers seven entries (index 0..6):
/// <list type="bullet">
/// <item>High-Speed and faster devices store the index itself as bInterval
/// (an exponent of 125 µs micro-frames): rate = 8000 &gt;&gt; (bInterval - 1).</item>
/// <item>Low/Full-Speed devices store milliseconds {1, 2, 4, 8, 16, 32}:
/// rate = 1000 / bInterval.</item>
/// <item>Index 0 deletes the value so the device descriptor applies.</item>
/// </list>
/// </summary>
public static class PollingRates
{
    public const int MaxIndex = 6;

    private static readonly int[] FullSpeedMilliseconds = [0, 1, 2, 4, 8, 16, 32];

    // Labels exactly as the setup prints them for Low/Full-Speed devices.
    private static readonly int[] FullSpeedHz = [0, 1000, 500, 250, 125, 62, 31];

    public static bool UsesMicroframes(UsbBusSpeed speed) =>
        speed is UsbBusSpeed.High or UsbBusSpeed.Super or UsbBusSpeed.SuperPlus;

    public static IReadOnlyList<PollingRateOption> OptionsFor(UsbBusSpeed speed)
    {
        if (speed == UsbBusSpeed.Unknown)
        {
            return [];
        }

        var options = new List<PollingRateOption>(MaxIndex + 1);
        for (var index = 0; index <= MaxIndex; index++)
        {
            options.Add(OptionAt(speed, index));
        }

        return options;
    }

    public static PollingRateOption OptionAt(UsbBusSpeed speed, int index)
    {
        if (index is < 0 or > MaxIndex)
        {
            throw new ArgumentOutOfRangeException(nameof(index));
        }

        if (index == 0)
        {
            return new PollingRateOption(0, null, null);
        }

        return UsesMicroframes(speed)
            ? new PollingRateOption(index, index, 8000 >> (index - 1))
            : new PollingRateOption(index, FullSpeedMilliseconds[index], FullSpeedHz[index]);
    }

    /// <summary>
    /// Maps a stored registry value back to the option the setup would show.
    /// Mirrors the setup: micro-frame values are clamped to 6; millisecond
    /// values select the first entry whose interval is &gt;= the stored value.
    /// </summary>
    public static PollingRateOption FromRegistry(UsbBusSpeed speed, int? storedBInterval)
    {
        if (storedBInterval is not { } stored || stored <= 0)
        {
            return OptionAt(speed, 0);
        }

        if (UsesMicroframes(speed))
        {
            return OptionAt(speed, Math.Min(stored, MaxIndex));
        }

        for (var index = 1; index <= MaxIndex; index++)
        {
            if (FullSpeedMilliseconds[index] >= stored)
            {
                return OptionAt(speed, index);
            }
        }

        return OptionAt(speed, MaxIndex);
    }

    /// <summary>Effective rate of an endpoint bInterval as the host schedules it.</summary>
    public static double? EndpointHz(UsbBusSpeed speed, int bInterval)
    {
        if (bInterval <= 0)
        {
            return null;
        }

        if (UsesMicroframes(speed))
        {
            // USB 2.0 §9.6.6: period = 2^(bInterval-1) micro-frames, valid 1..16.
            return bInterval > 16 ? null : 8000.0 / (1 << (bInterval - 1));
        }

        if (speed == UsbBusSpeed.Unknown)
        {
            return null;
        }

        // Windows schedules Low/Full-Speed interrupt endpoints on the largest
        // power-of-two frame period not above bInterval, capped at 32 ms.
        var period = 1;
        while (period * 2 <= Math.Min(bInterval, 32))
        {
            period *= 2;
        }

        return 1000.0 / period;
    }
}
