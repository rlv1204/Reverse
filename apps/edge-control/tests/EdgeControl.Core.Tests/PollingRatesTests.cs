using EdgeControl.Core.Overclock;

namespace EdgeControl.Core.Tests;

public class PollingRatesTests
{
    [Fact]
    public void HighSpeedOptionsMatchSetupMicroframeTable()
    {
        var options = PollingRates.OptionsFor(UsbBusSpeed.High);

        Assert.Equal([null, 8000, 4000, 2000, 1000, 500, 250], options.Select(o => o.Hz));
        Assert.Equal([null, 1, 2, 3, 4, 5, 6], options.Select(o => o.RegistryBInterval));
    }

    [Fact]
    public void FullSpeedOptionsMatchSetupMillisecondTable()
    {
        var options = PollingRates.OptionsFor(UsbBusSpeed.Full);

        Assert.Equal([null, 1000, 500, 250, 125, 62, 31], options.Select(o => o.Hz));
        Assert.Equal([null, 1, 2, 4, 8, 16, 32], options.Select(o => o.RegistryBInterval));
    }

    [Fact]
    public void UnknownSpeedOffersNothing() => Assert.Empty(PollingRates.OptionsFor(UsbBusSpeed.Unknown));

    [Theory]
    [InlineData(UsbBusSpeed.High, null, 0)]
    [InlineData(UsbBusSpeed.High, 1, 1)]
    [InlineData(UsbBusSpeed.High, 9, 6)]
    [InlineData(UsbBusSpeed.Full, 3, 3)]
    [InlineData(UsbBusSpeed.Full, 8, 4)]
    [InlineData(UsbBusSpeed.Full, 64, 6)]
    public void FromRegistryMirrorsSetupReadBack(UsbBusSpeed speed, int? stored, int expectedIndex) =>
        Assert.Equal(expectedIndex, PollingRates.FromRegistry(speed, stored).Index);

    [Theory]
    [InlineData(UsbBusSpeed.High, 1, 8000.0)]
    [InlineData(UsbBusSpeed.High, 4, 1000.0)]
    [InlineData(UsbBusSpeed.High, 6, 250.0)]
    [InlineData(UsbBusSpeed.Full, 1, 1000.0)]
    [InlineData(UsbBusSpeed.Full, 10, 125.0)]
    public void EndpointHzFollowsUsbScheduling(UsbBusSpeed speed, int bInterval, double hz) =>
        Assert.Equal(hz, PollingRates.EndpointHz(speed, bInterval));
}
