using System.Collections.ObjectModel;
using EdgeControl.App.Services;
using EdgeControl.Core.Input;

namespace EdgeControl.App.ViewModels;

public sealed class ButtonChip : ObservableObject
{
    private bool _pressed;

    public required string Name { get; init; }
    public required EdgeButtons Flag { get; init; }
    public bool Pressed { get => _pressed; set => Set(ref _pressed, value); }
}

public sealed class InputTestViewModel : PageViewModel
{
    // Stick canvas is 120 px; the dot is 16 px, so it travels 0..104.
    private const double Travel = 104;

    private readonly ControllerSession _session;
    private double _leftX = Travel / 2, _leftY = Travel / 2, _rightX = Travel / 2, _rightY = Travel / 2;
    private double _l2, _r2;
    private string _rate = "—";
    private string _dropped = "0";
    private string _raw = "—";
    private bool _connected;

    public InputTestViewModel(ControllerSession session)
    {
        _session = session;
        Buttons = new ObservableCollection<ButtonChip>(
        [
            Chip("Cruz", EdgeButtons.Cross), Chip("Círculo", EdgeButtons.Circle), Chip("Quadrado", EdgeButtons.Square), Chip("Triângulo", EdgeButtons.Triangle),
            Chip("↑", EdgeButtons.DpadUp), Chip("→", EdgeButtons.DpadRight), Chip("↓", EdgeButtons.DpadDown), Chip("←", EdgeButtons.DpadLeft),
            Chip("L1", EdgeButtons.L1), Chip("R1", EdgeButtons.R1), Chip("L2", EdgeButtons.L2), Chip("R2", EdgeButtons.R2),
            Chip("L3", EdgeButtons.L3), Chip("R3", EdgeButtons.R3), Chip("Create", EdgeButtons.Create), Chip("Options", EdgeButtons.Options),
            Chip("PS", EdgeButtons.PS), Chip("Touchpad", EdgeButtons.Touchpad), Chip("Mudo", EdgeButtons.Mute),
            Chip("Fn esq.", EdgeButtons.LeftFn), Chip("Fn dir.", EdgeButtons.RightFn), Chip("Traseiro esq.", EdgeButtons.LeftBack), Chip("Traseiro dir.", EdgeButtons.RightBack),
        ]);
    }

    public ObservableCollection<ButtonChip> Buttons { get; }
    public bool Connected { get => _connected; private set => Set(ref _connected, value); }
    public double LeftX { get => _leftX; private set => Set(ref _leftX, value); }
    public double LeftY { get => _leftY; private set => Set(ref _leftY, value); }
    public double RightX { get => _rightX; private set => Set(ref _rightX, value); }
    public double RightY { get => _rightY; private set => Set(ref _rightY, value); }
    public double L2 { get => _l2; private set => Set(ref _l2, value); }
    public double R2 { get => _r2; private set => Set(ref _r2, value); }
    public string Rate { get => _rate; private set => Set(ref _rate, value); }
    public string Dropped { get => _dropped; private set => Set(ref _dropped, value); }
    public string Raw { get => _raw; private set => Set(ref _raw, value); }

    private static ButtonChip Chip(string name, EdgeButtons flag) => new() { Name = name, Flag = flag };

    public override void Tick()
    {
        var report = _session.Latest;
        Connected = report is not null;
        if (report is not { } r)
        {
            Rate = "—";
            return;
        }

        LeftX = r.LeftX / 255.0 * Travel;
        LeftY = r.LeftY / 255.0 * Travel;
        RightX = r.RightX / 255.0 * Travel;
        RightY = r.RightY / 255.0 * Travel;
        L2 = r.L2;
        R2 = r.R2;
        foreach (var chip in Buttons)
        {
            chip.Pressed = (r.Buttons & chip.Flag) != 0;
        }

        Rate = $"{_session.RateHz:0} Hz";
        Dropped = _session.DroppedReports.ToString();
        Raw = $"LX {r.LeftX,3}  LY {r.LeftY,3}  RX {r.RightX,3}  RY {r.RightY,3}  L2 {r.L2,3}  R2 {r.R2,3}  seq {r.Sequence,3}";
    }
}
