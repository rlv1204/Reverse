using EdgeControl.Core.Overclock;

namespace EdgeControl.Core.Tests;

public class OverclockPlannerTests
{
    private static OverclockFacts Facts(
        UsbBusSpeed speed = UsbBusSpeed.High,
        string[]? filters = null,
        int? stored = null,
        int problem = 0,
        HidUsbfServiceState service = HidUsbfServiceState.Installed,
        string? controller = "USBXHCI") => new()
    {
        InstanceId = @"USB\VID_054C&PID_0DF2\5&1234&0&3",
        BusSpeed = speed,
        LowerFilters = filters ?? [],
        StoredBInterval = stored,
        ProblemCode = problem,
        Service = service,
        ControllerService = controller,
    };

    [Fact]
    public void EightKilohertzAddsFilterWritesValueAndRestarts()
    {
        var plan = OverclockPlanner.Plan(Facts(), 1);

        Assert.False(plan.IsBlocked);
        Assert.Equal(["hidusbf"], plan.NewLowerFilters);
        Assert.Equal(
            [ChangeKind.AddFilter, ChangeKind.SetBInterval, ChangeKind.RestartDevice],
            plan.Changes.Select(c => c.Kind));
        Assert.Equal(1, plan.Changes[1].Value);
        Assert.Contains(plan.Warnings, w => w.Code == "above-1000hz");
    }

    [Fact]
    public void DefaultRemovesOnlyHidusbfAndDeletesValue()
    {
        var plan = OverclockPlanner.Plan(Facts(filters: ["other", "HIDUSBF"], stored: 1), 0);

        Assert.Equal(["other"], plan.NewLowerFilters);
        Assert.Equal(
            [ChangeKind.RemoveFilter, ChangeKind.DeleteBInterval, ChangeKind.RestartDevice],
            plan.Changes.Select(c => c.Kind));
        Assert.Empty(plan.Warnings);
    }

    [Fact]
    public void RestoringDefaultIsNeverBlocked()
    {
        var plan = OverclockPlanner.Plan(
            Facts(filters: ["hidusbf"], stored: 1, problem: 10, service: HidUsbfServiceState.NotInstalled),
            0);

        Assert.False(plan.IsBlocked);
        Assert.Equal(ChangeKind.RemoveFilter, plan.Changes[0].Kind);
    }

    [Theory]
    [InlineData(HidUsbfServiceState.NotInstalled)]
    [InlineData(HidUsbfServiceState.Disabled)]
    [InlineData(HidUsbfServiceState.DriverFileMissing)]
    public void OverclockRequiresWorkingDriver(HidUsbfServiceState state) =>
        Assert.True(OverclockPlanner.Plan(Facts(service: state), 4).IsBlocked);

    [Fact]
    public void OverclockIsBlockedForDeviceWithProblem() =>
        Assert.True(OverclockPlanner.Plan(Facts(problem: 43), 4).IsBlocked);

    [Fact]
    public void UnknownSpeedBlocksEverything() =>
        Assert.True(OverclockPlanner.Plan(Facts(speed: UsbBusSpeed.Unknown), 0).IsBlocked);

    [Fact]
    public void UnknownControllerNeedsAcknowledgement()
    {
        var plan = OverclockPlanner.Plan(Facts(controller: "VIAXHCI"), 4);

        Assert.False(plan.IsBlocked);
        Assert.Contains(plan.Warnings, w => w.Code == "unknown-controller");
        Assert.DoesNotContain(plan.Warnings, w => w.Code == "above-1000hz");
    }

    [Fact]
    public void AlreadyAppliedIsNoOp() =>
        Assert.True(OverclockPlanner.Plan(Facts(filters: ["hidusbf"], stored: 1), 1).IsNoOp);

    [Fact]
    public void ExistingFilterIsKeptInPlace()
    {
        var plan = OverclockPlanner.Plan(Facts(filters: ["a", "hidusbf"]), 4);

        Assert.Equal(["a", "hidusbf"], plan.NewLowerFilters);
        Assert.DoesNotContain(plan.Changes, c => c.Kind == ChangeKind.AddFilter);
    }
}
