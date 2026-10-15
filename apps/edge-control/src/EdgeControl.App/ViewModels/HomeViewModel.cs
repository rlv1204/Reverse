using EdgeControl.App.Services;
using EdgeControl.Core.Input;

namespace EdgeControl.App.ViewModels;

public sealed class HomeViewModel : PageViewModel
{
    private readonly ControllerSession _session;
    private readonly OverclockViewModel _overclock;
    private string _battery = "—";
    private string _firmware = "—";
    private string _hardware = "—";
    private string _buildDate = "—";
    private string _measuredRate = "—";
    private bool _connected;
    private int _batteryPercent;

    public HomeViewModel(ControllerSession session, OverclockViewModel overclock)
    {
        _session = session;
        _overclock = overclock;
    }

    public bool Connected { get => _connected; private set => Set(ref _connected, value); }
    public string Battery { get => _battery; private set => Set(ref _battery, value); }
    public int BatteryPercent { get => _batteryPercent; private set => Set(ref _batteryPercent, value); }
    public string Firmware { get => _firmware; private set => Set(ref _firmware, value); }
    public string Hardware { get => _hardware; private set => Set(ref _hardware, value); }
    public string BuildDate { get => _buildDate; private set => Set(ref _buildDate, value); }
    public string MeasuredRate { get => _measuredRate; private set => Set(ref _measuredRate, value); }
    public string ConfiguredRate => _overclock.ConfiguredRateText;

    public override void OnShown() => _overclock.Refresh();

    public override void Tick()
    {
        var report = _session.Latest;
        Connected = report is not null;
        if (report is { } r)
        {
            BatteryPercent = r.Battery.Percent;
            Battery = r.Battery.State switch
            {
                ChargingState.Charging => $"{r.Battery.Percent}% · carregando",
                ChargingState.Full => "100% · carga completa",
                ChargingState.Error => "Erro de carga informado pelo controle",
                _ => $"{r.Battery.Percent}%",
            };
            MeasuredRate = $"{_session.RateHz:0} Hz";
        }
        else
        {
            Battery = "—";
            BatteryPercent = 0;
            MeasuredRate = "—";
        }

        var fw = _session.Firmware;
        Firmware = fw is null ? "—" : $"0x{fw.FirmwareVersion:X8} (atualização {fw.UpdateVersionText})";
        Hardware = fw is null ? "—" : $"0x{fw.HardwareVersion:X8}";
        BuildDate = fw is null ? "—" : $"{fw.BuildDate} {fw.BuildTime}";
        OnPropertyChanged(nameof(ConfiguredRate));
    }
}
