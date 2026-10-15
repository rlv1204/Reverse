namespace EdgeControl.Core.Overclock;

/// <summary>Facts observed on the target machine before any change.</summary>
public sealed record OverclockFacts
{
    public required string InstanceId { get; init; }
    public required UsbBusSpeed BusSpeed { get; init; }
    public required IReadOnlyList<string> LowerFilters { get; init; }

    /// <summary>Raw "bInterval" DWORD from the driver key; null when absent.</summary>
    public required int? StoredBInterval { get; init; }

    /// <summary>CM problem code; 0 means the device works.</summary>
    public required int ProblemCode { get; init; }

    public required HidUsbfServiceState Service { get; init; }

    /// <summary>Service name of the USB host controller driver, e.g. USBXHCI.</summary>
    public required string? ControllerService { get; init; }
}

public enum HidUsbfServiceState
{
    NotInstalled,
    Disabled,
    DriverFileMissing,
    Installed,
}

public enum ChangeKind
{
    AddFilter,
    RemoveFilter,
    SetBInterval,
    DeleteBInterval,
    RestartDevice,
}

public sealed record PlannedChange(ChangeKind Kind, string Description, int? Value = null);

/// <summary>
/// A warning the user must acknowledge explicitly before the plan may run.
/// </summary>
public sealed record SafetyWarning(string Code, string Message);

public sealed record OverclockPlan(
    PollingRateOption Target,
    IReadOnlyList<string> NewLowerFilters,
    IReadOnlyList<PlannedChange> Changes,
    IReadOnlyList<string> Blockers,
    IReadOnlyList<SafetyWarning> Warnings)
{
    public bool IsBlocked => Blockers.Count > 0;
    public bool IsNoOp => !IsBlocked && Changes.Count == 0;
}

/// <summary>
/// Decides what may be written. Restoring the default is never blocked so
/// the user can always undo; raising the rate is refused when the setup's
/// own preconditions are not met.
/// </summary>
public static class OverclockPlanner
{
    /// <summary>Host controller services the hidusbf setup recognises.</summary>
    public static readonly IReadOnlyList<string> KnownControllerServices =
    [
        "USBXHCI", "USBEHCI", "USBUHCI", "USBOHCI", "UHCD", "OPENHCI", "IUSB3XHC", "XHCDRV",
    ];

    public const int HighRateThresholdHz = 1000;

    public static OverclockPlan Plan(OverclockFacts facts, int targetIndex)
    {
        var blockers = new List<string>();
        var warnings = new List<SafetyWarning>();

        if (facts.BusSpeed == UsbBusSpeed.Unknown)
        {
            return new OverclockPlan(
                new PollingRateOption(targetIndex, null, null),
                facts.LowerFilters,
                [],
                ["Não foi possível ler a velocidade USB do controle. Reconecte o cabo e tente novamente."],
                []);
        }

        var target = PollingRates.OptionAt(facts.BusSpeed, targetIndex);
        var filterPresent = LowerFilters.Contains(facts.LowerFilters);
        var wantFilter = !target.IsDefault;

        if (wantFilter)
        {
            switch (facts.Service)
            {
                case HidUsbfServiceState.NotInstalled:
                    blockers.Add("O driver hidusbf não está instalado. Instale-o pelo Setup oficial do hidusbf (botão \"Install Service\") e reabra este app.");
                    break;
                case HidUsbfServiceState.Disabled:
                    blockers.Add("O serviço hidusbf está desativado no Windows. Reinstale-o pelo Setup oficial do hidusbf.");
                    break;
                case HidUsbfServiceState.DriverFileMissing:
                    blockers.Add("O serviço hidusbf existe, mas o arquivo drivers\\hidusbf.sys não foi encontrado.");
                    break;
            }

            if (facts.ProblemCode != 0)
            {
                blockers.Add($"O controle está com problema no Gerenciador de Dispositivos (código {facts.ProblemCode}). Resolva antes de aplicar overclock.");
            }

            if (facts.ControllerService is not { } controller
                || !KnownControllerServices.Contains(controller, StringComparer.OrdinalIgnoreCase))
            {
                warnings.Add(new SafetyWarning(
                    "unknown-controller",
                    $"O driver da controladora USB (\"{facts.ControllerService ?? "desconhecido"}\") não é reconhecido pelo hidusbf. O overclock pode não funcionar e o controle pode parar de responder até ser reconectado. Se possível, use outra porta USB."));
            }

            if (target.Hz > HighRateThresholdHz)
            {
                warnings.Add(new SafetyWarning(
                    "above-1000hz",
                    $"{target.Hz} Hz está acima do padrão de 1000 Hz. Isso aumenta o uso de CPU e pode causar instabilidade em algumas controladoras USB. Não altera tensão nem corrente do cabo."));
            }

            if (facts.BusSpeed == UsbBusSpeed.Low && target.Hz > 125)
            {
                warnings.Add(new SafetyWarning(
                    "speed-class",
                    "Overclock acima da classe de velocidade USB do dispositivo exige a versão \"Patching\" do hidusbf.sys e Integridade de Memória desativada."));
            }
        }

        var newFilters = LowerFilters.WithHidUsbf(facts.LowerFilters, wantFilter);
        var changes = new List<PlannedChange>();

        if (wantFilter && !filterPresent)
        {
            changes.Add(new PlannedChange(ChangeKind.AddFilter, "Adicionar o filtro hidusbf ao controle"));
        }
        else if (!wantFilter && filterPresent)
        {
            changes.Add(new PlannedChange(ChangeKind.RemoveFilter, "Remover o filtro hidusbf do controle"));
        }

        if (target.RegistryBInterval is { } value)
        {
            if (facts.StoredBInterval != value)
            {
                changes.Add(new PlannedChange(ChangeKind.SetBInterval, $"Gravar bInterval = {value} ({target.Label})", value));
            }
        }
        else if (facts.StoredBInterval is not null)
        {
            changes.Add(new PlannedChange(ChangeKind.DeleteBInterval, "Apagar bInterval (voltar ao padrão do controle)"));
        }

        if (changes.Count > 0)
        {
            changes.Add(new PlannedChange(ChangeKind.RestartDevice, "Reiniciar o controle para aplicar"));
        }

        return new OverclockPlan(target, newFilters, changes, blockers, warnings);
    }
}
