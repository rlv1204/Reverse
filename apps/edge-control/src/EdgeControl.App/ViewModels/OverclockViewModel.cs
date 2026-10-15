using System.Collections.ObjectModel;
using System.Windows;
using EdgeControl.App.Services;
using EdgeControl.Core.Overclock;
using EdgeControl.Windows;

namespace EdgeControl.App.ViewModels;

public sealed class RateTile : ObservableObject
{
    private bool _isSelected;

    public required PollingRateOption Option { get; init; }
    public required bool IsConfigured { get; init; }
    public string Title => Option.Hz is { } hz ? $"{hz} Hz" : "Padrão";
    public string Subtitle => Option.Hz is { } hz ? $"{1000.0 / hz:0.###} ms" : "sem overclock";
    public bool IsSelected { get => _isSelected; set => Set(ref _isSelected, value); }
}

public sealed class WarningItem : ObservableObject
{
    private bool _acknowledged;

    public required SafetyWarning Warning { get; init; }
    public bool Acknowledged { get => _acknowledged; set => Set(ref _acknowledged, value); }
}

public sealed class OverclockViewModel : PageViewModel
{
    private readonly ControllerSession _session;
    private readonly OverclockService _service = new(OverclockService.DefaultBackupDirectory);
    private EdgeUsbDevice? _device;
    private HidUsbfStatus? _driver;
    private OverclockPlan? _plan;
    private RateTile? _selectedTile;
    private bool _busy;
    private string _measured = "—";

    public OverclockViewModel(ControllerSession session, bool isElevated)
    {
        _session = session;
        IsElevated = isElevated;
        RefreshCommand = new RelayCommand(Refresh, () => !_busy);
        ApplyCommand = new RelayCommand(ApplySelectedAsync, CanApply);
        RestoreCommand = new RelayCommand(RestoreDefaultAsync, () => !_busy && _device is not null && IsElevated);
        CopyDiagnosticCommand = new RelayCommand(CopyDiagnostic, () => _device is not null);
        Warnings.CollectionChanged += (_, _) => OnPropertyChanged(nameof(HasWarnings));
    }

    public bool IsElevated { get; }
    public RelayCommand RefreshCommand { get; }
    public RelayCommand ApplyCommand { get; }
    public RelayCommand RestoreCommand { get; }
    public RelayCommand CopyDiagnosticCommand { get; }

    public ObservableCollection<RateTile> Tiles { get; } = [];
    public ObservableCollection<WarningItem> Warnings { get; } = [];
    public ObservableCollection<string> Blockers { get; } = [];
    public ObservableCollection<string> PlannedChanges { get; } = [];
    public ObservableCollection<string> Log { get; } = [];

    public bool HasDevice => _device is not null;
    public bool HasWarnings => Warnings.Count > 0;
    public bool Busy { get => _busy; private set => Set(ref _busy, value); }

    public string DeviceText => _device is null
        ? "Conecte o DualSense Edge pelo cabo USB."
        : $"{_device.Name}";

    public string InstanceText => _device?.InstanceId ?? "";

    public string DriverText => _driver?.State switch
    {
        HidUsbfServiceState.Installed => $"Instalado{(_driver.FileVersion is { } v ? $" · v{v}" : "")}",
        HidUsbfServiceState.Disabled => "Desativado",
        HidUsbfServiceState.DriverFileMissing => "Arquivo .sys ausente",
        HidUsbfServiceState.NotInstalled => "Não instalado",
        _ => "—",
    };

    public bool DriverOk => _driver?.State == HidUsbfServiceState.Installed;

    public string SpeedText => _device?.Speed switch
    {
        UsbBusSpeed.Low => "Low-Speed (1,5 Mbit/s)",
        UsbBusSpeed.Full => "Full-Speed (12 Mbit/s) · máx. 1000 Hz",
        UsbBusSpeed.High => "High-Speed (480 Mbit/s) · até 8000 Hz",
        UsbBusSpeed.Super or UsbBusSpeed.SuperPlus => "SuperSpeed · até 8000 Hz",
        null => "—",
        _ => "Desconhecida",
    };

    public string ControllerText => _device?.ControllerService is { } service
        ? $"{service}{(OverclockPlanner.KnownControllerServices.Contains(service, StringComparer.OrdinalIgnoreCase) ? " · reconhecida" : " · não reconhecida")}"
        : "—";

    public string MemoryIntegrityText => _driver?.MemoryIntegrity switch
    {
        ToggleState.On => "Ativada",
        ToggleState.Off => "Desativada",
        _ => "—",
    };

    public string FilterText => _device is null
        ? "—"
        : LowerFilters.Contains(_device.LowerFilters) ? "Ativo neste controle" : "Inativo";

    public string ConfiguredRateText => _device is null
        ? "—"
        : PollingRates.FromRegistry(_device.Speed, _device.StoredBInterval) is var option && option.Hz is { } hz && LowerFilters.Contains(_device.LowerFilters)
            ? $"{hz} Hz"
            : "Padrão do controle";

    /// <summary>Rate the hub schedules for the input endpoint right now (observed, not configured).</summary>
    public string EffectiveRateText
    {
        get
        {
            var pipe = _device?.InterruptInPipes.FirstOrDefault();
            if (_device is null || pipe is null)
            {
                return "—";
            }

            return PollingRates.EndpointHz(_device.Speed, pipe.BInterval) is { } hz
                ? $"{hz:0} Hz (bInterval {pipe.BInterval})"
                : $"bInterval {pipe.BInterval}";
        }
    }

    public string MeasuredRateText { get => _measured; private set => Set(ref _measured, value); }

    public string InterfaceFilterNote => _device?.Interfaces.FirstOrDefault(i => LowerFilters.Contains(i.LowerFilters)) is { } node
        ? $"Atenção: há um filtro hidusbf antigo na interface {node.InstanceId}. Este app configura o nó USB principal; use \"Copiar diagnóstico\" e me envie o resultado."
        : "";

    public RateTile? SelectedTile
    {
        get => _selectedTile;
        set
        {
            if (Set(ref _selectedTile, value))
            {
                foreach (var tile in Tiles)
                {
                    tile.IsSelected = ReferenceEquals(tile, value);
                }

                Replan();
            }
        }
    }

    public override void OnShown() => Refresh();

    public override void Tick()
    {
        MeasuredRateText = _session.Latest is null ? "—" : $"{_session.RateHz:0} Hz";
    }

    public void Refresh()
    {
        try
        {
            _driver = HidUsbfStatus.Read();
            _device = EdgeUsbDevices.FindPresent().FirstOrDefault();
        }
        catch (Exception error)
        {
            AddLog($"Erro ao ler o dispositivo: {error.Message}");
            _device = null;
        }

        var previous = _selectedTile?.Option.Index;
        Tiles.Clear();
        if (_device is not null)
        {
            var configured = PollingRates.FromRegistry(_device.Speed, _device.StoredBInterval);
            var configuredIndex = LowerFilters.Contains(_device.LowerFilters) ? configured.Index : 0;

            // Show slowest to fastest, default first.
            foreach (var option in PollingRates.OptionsFor(_device.Speed).OrderBy(o => o.Hz ?? 0))
            {
                Tiles.Add(new RateTile { Option = option, IsConfigured = option.Index == configuredIndex });
            }

            _selectedTile = null;
            SelectedTile = Tiles.FirstOrDefault(t => t.Option.Index == (previous ?? configuredIndex)) ?? Tiles.FirstOrDefault();
        }
        else
        {
            _selectedTile = null;
            Replan();
        }

        foreach (var name in new[]
        {
            nameof(HasDevice), nameof(DeviceText), nameof(InstanceText), nameof(DriverText), nameof(DriverOk), nameof(SpeedText),
            nameof(ControllerText), nameof(MemoryIntegrityText), nameof(FilterText), nameof(ConfiguredRateText),
            nameof(EffectiveRateText), nameof(InterfaceFilterNote), nameof(SelectedTile),
        })
        {
            OnPropertyChanged(name);
        }
    }

    private void Replan()
    {
        Warnings.Clear();
        Blockers.Clear();
        PlannedChanges.Clear();
        _plan = null;

        if (_device is null || _driver is null || _selectedTile is null)
        {
            return;
        }

        _plan = OverclockPlanner.Plan(_device.ToFacts(_driver), _selectedTile.Option.Index);
        if (!IsElevated)
        {
            Blockers.Add("Abra o Edge Control como administrador para alterar a taxa.");
        }

        foreach (var blocker in _plan.Blockers) Blockers.Add(blocker);
        foreach (var warning in _plan.Warnings) Warnings.Add(new WarningItem { Warning = warning });
        foreach (var change in _plan.Changes) PlannedChanges.Add(change.Description);
        if (_plan.IsNoOp)
        {
            PlannedChanges.Add("Nada a alterar: esta taxa já está configurada.");
        }
    }

    private bool CanApply() =>
        !_busy && IsElevated && _plan is { IsBlocked: false, IsNoOp: false } && Warnings.All(w => w.Acknowledged);

    private Task ApplySelectedAsync() => ApplyAsync(_selectedTile?.Option.Index ?? 0, Warnings.Where(w => w.Acknowledged).Select(w => w.Warning.Code));

    private Task RestoreDefaultAsync() => ApplyAsync(0, []);

    private async Task ApplyAsync(int index, IEnumerable<string> acknowledged)
    {
        if (_device is not { } device)
        {
            return;
        }

        var label = PollingRates.OptionAt(device.Speed, index).Label;
        var confirm = MessageBox.Show(
            $"Aplicar \"{label}\"?\n\nO controle será reiniciado (desconecta por alguns segundos). " +
            "Se ele não voltar a funcionar em 15 s, a configuração anterior será restaurada automaticamente.",
            "Overclock USB", MessageBoxButton.OKCancel, MessageBoxImage.Question);
        if (confirm != MessageBoxResult.OK)
        {
            return;
        }

        Busy = true;
        var instanceId = device.InstanceId;
        _session.Pause();
        try
        {
            var progress = new Progress<string>(AddLog);
            var result = await _service.ApplyAsync(instanceId, index, acknowledged.ToHashSet(), progress);
            AddLog(result.Message);
            var icon = result.Outcome switch
            {
                ApplyOutcome.Applied or ApplyOutcome.NothingToDo => MessageBoxImage.Information,
                ApplyOutcome.AppliedNeedsReboot or ApplyOutcome.RolledBack or ApplyOutcome.Blocked => MessageBoxImage.Warning,
                _ => MessageBoxImage.Error,
            };
            MessageBox.Show(result.Message, "Overclock USB", MessageBoxButton.OK, icon);
        }
        catch (Exception error)
        {
            AddLog($"Erro: {error.Message}");
            MessageBox.Show(error.Message, "Overclock USB", MessageBoxButton.OK, MessageBoxImage.Error);
        }
        finally
        {
            _session.Resume();
            Busy = false;
            Refresh();
        }
    }

    private void CopyDiagnostic()
    {
        if (_device is null || _driver is null)
        {
            return;
        }

        Clipboard.SetText(_device.Diagnostic(_driver));
        AddLog("Diagnóstico copiado para a área de transferência.");
    }

    private void AddLog(string line) => Log.Insert(0, $"{DateTime.Now:HH:mm:ss}  {line}");
}
