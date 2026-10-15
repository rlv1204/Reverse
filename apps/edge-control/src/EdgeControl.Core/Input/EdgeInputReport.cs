namespace EdgeControl.Core.Input;

[Flags]
public enum EdgeButtons : uint
{
    None = 0,
    Square = 1 << 0,
    Cross = 1 << 1,
    Circle = 1 << 2,
    Triangle = 1 << 3,
    L1 = 1 << 4,
    R1 = 1 << 5,
    L2 = 1 << 6,
    R2 = 1 << 7,
    Create = 1 << 8,
    Options = 1 << 9,
    L3 = 1 << 10,
    R3 = 1 << 11,
    PS = 1 << 12,
    Touchpad = 1 << 13,
    Mute = 1 << 14,
    LeftFn = 1 << 15,
    RightFn = 1 << 16,
    LeftBack = 1 << 17,
    RightBack = 1 << 18,
    DpadUp = 1 << 19,
    DpadRight = 1 << 20,
    DpadDown = 1 << 21,
    DpadLeft = 1 << 22,
}

public enum ChargingState
{
    Discharging,
    Charging,
    Full,
    Error,
    Unknown,
}

public readonly record struct BatteryStatus(int Percent, ChargingState State);

/// <summary>
/// Input report 0x01 over USB (64 bytes). Layout follows the public
/// DualSense definition (Linux hid-playstation.c, struct dualsense_input_report);
/// the Edge reuses it. The Fn/back-button bits in buttons[2] follow SDL's
/// hidapi PS5 driver and are verified with the input test page.
/// </summary>
public readonly record struct EdgeInputReport(
    byte LeftX,
    byte LeftY,
    byte RightX,
    byte RightY,
    byte L2,
    byte R2,
    byte Sequence,
    EdgeButtons Buttons,
    BatteryStatus Battery,
    uint SensorTimestamp)
{
    public const byte UsbReportId = 0x01;
    public const int UsbReportLength = 64;

    public static bool TryParseUsb(ReadOnlySpan<byte> report, out EdgeInputReport parsed)
    {
        parsed = default;
        if (report.Length < UsbReportLength || report[0] != UsbReportId)
        {
            return false;
        }

        var b0 = report[8];
        var b1 = report[9];
        var b2 = report[10];
        var buttons = DecodeHat(b0 & 0x0F);
        if ((b0 & 0x10) != 0) buttons |= EdgeButtons.Square;
        if ((b0 & 0x20) != 0) buttons |= EdgeButtons.Cross;
        if ((b0 & 0x40) != 0) buttons |= EdgeButtons.Circle;
        if ((b0 & 0x80) != 0) buttons |= EdgeButtons.Triangle;
        if ((b1 & 0x01) != 0) buttons |= EdgeButtons.L1;
        if ((b1 & 0x02) != 0) buttons |= EdgeButtons.R1;
        if ((b1 & 0x04) != 0) buttons |= EdgeButtons.L2;
        if ((b1 & 0x08) != 0) buttons |= EdgeButtons.R2;
        if ((b1 & 0x10) != 0) buttons |= EdgeButtons.Create;
        if ((b1 & 0x20) != 0) buttons |= EdgeButtons.Options;
        if ((b1 & 0x40) != 0) buttons |= EdgeButtons.L3;
        if ((b1 & 0x80) != 0) buttons |= EdgeButtons.R3;
        if ((b2 & 0x01) != 0) buttons |= EdgeButtons.PS;
        if ((b2 & 0x02) != 0) buttons |= EdgeButtons.Touchpad;
        if ((b2 & 0x04) != 0) buttons |= EdgeButtons.Mute;
        if ((b2 & 0x10) != 0) buttons |= EdgeButtons.LeftFn;
        if ((b2 & 0x20) != 0) buttons |= EdgeButtons.RightFn;
        if ((b2 & 0x40) != 0) buttons |= EdgeButtons.LeftBack;
        if ((b2 & 0x80) != 0) buttons |= EdgeButtons.RightBack;

        var timestamp = (uint)(report[28] | report[29] << 8 | report[30] << 16 | report[31] << 24);

        parsed = new EdgeInputReport(
            report[1], report[2], report[3], report[4], report[5], report[6], report[7],
            buttons, DecodeBattery(report[53]), timestamp);
        return true;
    }

    private static EdgeButtons DecodeHat(int hat) => hat switch
    {
        0 => EdgeButtons.DpadUp,
        1 => EdgeButtons.DpadUp | EdgeButtons.DpadRight,
        2 => EdgeButtons.DpadRight,
        3 => EdgeButtons.DpadRight | EdgeButtons.DpadDown,
        4 => EdgeButtons.DpadDown,
        5 => EdgeButtons.DpadDown | EdgeButtons.DpadLeft,
        6 => EdgeButtons.DpadLeft,
        7 => EdgeButtons.DpadLeft | EdgeButtons.DpadUp,
        _ => EdgeButtons.None,
    };

    /// <summary>
    /// Low nibble is capacity in tenths, high nibble is the charging state
    /// (hid-playstation: 0 discharging, 1 charging, 2 full, 0xA/0xB voltage
    /// or temperature error, 0xF charging error).
    /// </summary>
    private static BatteryStatus DecodeBattery(byte status)
    {
        var level = status & 0x0F;
        var stateCode = status >> 4;
        var state = stateCode switch
        {
            0x0 => ChargingState.Discharging,
            0x1 => ChargingState.Charging,
            0x2 => ChargingState.Full,
            0xA or 0xB or 0xF => ChargingState.Error,
            _ => ChargingState.Unknown,
        };

        var percent = state == ChargingState.Full ? 100 : Math.Min(level * 10 + 5, 100);
        return new BatteryStatus(percent, state);
    }
}
