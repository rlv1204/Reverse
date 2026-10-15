using System.Text;

namespace EdgeControl.Core.Input;

/// <summary>
/// Feature report 0x20 (read-only GET). Offsets follow Linux hid-playstation.c:
/// build date at 1 (11 chars), build time at 12 (8 chars), hardware version
/// LE32 at 24, firmware version LE32 at 28, update version LE16 at 44.
/// </summary>
public sealed record FirmwareInfo(string BuildDate, string BuildTime, uint HardwareVersion, uint FirmwareVersion, ushort UpdateVersion)
{
    public const byte ReportId = 0x20;
    public const int ReportLength = 64;

    public string UpdateVersionText => $"{UpdateVersion >> 8:X2}.{UpdateVersion & 0xFF:X2}";

    public static FirmwareInfo? TryParse(ReadOnlySpan<byte> report)
    {
        if (report.Length < ReportLength || report[0] != ReportId)
        {
            return null;
        }

        static string Ascii(ReadOnlySpan<byte> bytes) => Encoding.ASCII.GetString(bytes).TrimEnd('\0', ' ');

        return new FirmwareInfo(
            Ascii(report.Slice(1, 11)),
            Ascii(report.Slice(12, 8)),
            BitConverter.ToUInt32(report.Slice(24, 4)),
            BitConverter.ToUInt32(report.Slice(28, 4)),
            BitConverter.ToUInt16(report.Slice(44, 2)));
    }
}
