using EdgeControl.Core.Devices;
using EdgeControl.Core.Input;
using EdgeControl.Core.Overclock;

namespace EdgeControl.Core.Tests;

public class InputTests
{
    private static byte[] NeutralReport()
    {
        var r = new byte[64];
        r[0] = 0x01;
        r[1] = r[2] = r[3] = r[4] = 0x80;
        r[8] = 0x08; // hat released
        return r;
    }

    [Fact]
    public void ParsesSticksTriggersAndFaceButtons()
    {
        var r = NeutralReport();
        r[1] = 0x00;
        r[6] = 0xFF;
        r[7] = 42;
        r[8] = 0x20 | 0x02; // cross + hat right
        r[9] = 0x01 | 0x20; // L1 + options
        r[10] = 0x10 | 0x80; // left Fn + right back
        r[53] = 0x15; // charging, level 5

        Assert.True(EdgeInputReport.TryParseUsb(r, out var p));
        Assert.Equal(0, p.LeftX);
        Assert.Equal(255, p.R2);
        Assert.Equal(42, p.Sequence);
        Assert.Equal(
            EdgeButtons.Cross | EdgeButtons.DpadRight | EdgeButtons.L1 | EdgeButtons.Options | EdgeButtons.LeftFn | EdgeButtons.RightBack,
            p.Buttons);
        Assert.Equal(new BatteryStatus(55, ChargingState.Charging), p.Battery);
    }

    [Fact]
    public void RejectsBluetoothOrShortReports()
    {
        var r = NeutralReport();
        r[0] = 0x31;
        Assert.False(EdgeInputReport.TryParseUsb(r, out _));
        Assert.False(EdgeInputReport.TryParseUsb(new byte[10], out _));
    }

    [Fact]
    public void FullBatteryReportsHundred()
    {
        var r = NeutralReport();
        r[53] = 0x2A;
        Assert.True(EdgeInputReport.TryParseUsb(r, out var p));
        Assert.Equal(100, p.Battery.Percent);
    }

    [Fact]
    public void ParsesFirmwareFeatureReport()
    {
        var r = new byte[64];
        r[0] = 0x20;
        "Jun 10 2024"u8.CopyTo(r.AsSpan(1));
        "12:34:56"u8.CopyTo(r.AsSpan(12));
        BitConverter.GetBytes(0x00000619u).CopyTo(r, 24);
        BitConverter.GetBytes(0x01000123u).CopyTo(r, 28);
        BitConverter.GetBytes((ushort)0x0230).CopyTo(r, 44);

        var info = FirmwareInfo.TryParse(r);

        Assert.NotNull(info);
        Assert.Equal("Jun 10 2024", info.BuildDate);
        Assert.Equal(0x01000123u, info.FirmwareVersion);
        Assert.Equal("02.30", info.UpdateVersionText);
    }

    [Fact]
    public void RateMeterCountsDroppedReportsFromSequence()
    {
        var meter = new ReportRateMeter(TimeSpan.FromSeconds(1));
        byte seq = 0;
        for (var i = 0; i <= 1000; i++)
        {
            meter.Record(TimeSpan.FromMilliseconds(i), seq);
            seq += (byte)(i % 100 == 0 ? 2 : 1);
        }

        Assert.InRange(meter.RateHz(TimeSpan.FromMilliseconds(1000)), 990, 1020);
        Assert.Equal(10, meter.DroppedReports);
    }

    [Theory]
    [InlineData(@"USB\VID_054C&PID_0DF2\5&2A3B&0&4", true, false)]
    [InlineData(@"USB\VID_054C&PID_0DF2&MI_03\6&1&0&0003", false, true)]
    [InlineData(@"USB\VID_054C&PID_0CE6\5&2A3B&0&4", false, false)]
    public void ClassifiesInstanceIds(string id, bool device, bool iface)
    {
        Assert.Equal(device, EdgeIdentity.IsUsbDeviceNode(id));
        Assert.Equal(iface, EdgeIdentity.IsUsbInterfaceNode(id));
    }

    [Fact]
    public void ClassifiesHidPaths()
    {
        Assert.Equal(EdgeTransport.Usb, EdgeIdentity.ClassifyHidPath(@"\\?\hid#vid_054c&pid_0df2&mi_03#7&abc#{4d1e55b2-f16f-11cf-88cb-001111000030}"));
        Assert.Equal(EdgeTransport.Bluetooth, EdgeIdentity.ClassifyHidPath(@"\\?\hid#{00001124-0000-1000-8000-00805f9b34fb}_vid&0002054c_pid&0df2#8&x#{4d1e55b2}"));
        Assert.Equal(EdgeTransport.NotEdge, EdgeIdentity.ClassifyHidPath(@"\\?\hid#vid_046d&pid_c077#x"));
    }

    [Fact]
    public void BackupRoundTrips()
    {
        var backup = new OverclockBackup(@"USB\VID_054C&PID_0DF2\x", ["a", "hidusbf"], 4, DateTimeOffset.Parse("2026-10-15T10:00:00Z"));
        var copy = OverclockBackup.FromJson(backup.ToJson());

        Assert.NotNull(copy);
        Assert.Equal(backup.LowerFilters, copy.LowerFilters);
        Assert.Equal(4, copy.StoredBInterval);
        Assert.Equal("backup-20261015-100000.json", backup.FileName);
    }
}
