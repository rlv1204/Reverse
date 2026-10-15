using EdgeControl.Core.Overclock;
using EdgeControl.Windows.Native;
using static EdgeControl.Windows.Native.NativeMethods;

namespace EdgeControl.Windows;

public enum ApplyOutcome
{
    Applied,
    AppliedNeedsReboot,
    NothingToDo,
    Blocked,
    RolledBack,
    RollbackFailed,
}

public sealed record ApplyResult(ApplyOutcome Outcome, string Message, EdgeUsbDevice? Device, string? BackupPath);

/// <summary>
/// Writes the two registry entries hidusbf reads (device LowerFilters and the
/// driver-key "bInterval" DWORD), restarts the controller, and rolls back to
/// the saved values when it does not start again.
/// </summary>
public sealed class OverclockService
{
    public static readonly TimeSpan StartTimeout = TimeSpan.FromSeconds(15);

    public OverclockService(string backupDirectory)
    {
        BackupDirectory = backupDirectory;
    }

    public static string DefaultBackupDirectory =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "EdgeControl", "backups");

    public string BackupDirectory { get; }

    /// <param name="acknowledgedWarnings">Codes of the warnings the user confirmed.</param>
    public async Task<ApplyResult> ApplyAsync(string instanceId, int targetIndex, IReadOnlySet<string> acknowledgedWarnings, IProgress<string> progress)
    {
        // Plan from fresh facts so a stale screen can never drive a write.
        var device = EdgeUsbDevices.Refresh(instanceId);
        if (device is null)
        {
            return new ApplyResult(ApplyOutcome.Blocked, "O controle foi desconectado.", null, null);
        }

        var facts = device.ToFacts(HidUsbfStatus.Read());
        var plan = OverclockPlanner.Plan(facts, targetIndex);
        if (plan.IsBlocked)
        {
            return new ApplyResult(ApplyOutcome.Blocked, string.Join(Environment.NewLine, plan.Blockers), device, null);
        }

        var missing = plan.Warnings.Where(w => !acknowledgedWarnings.Contains(w.Code)).ToArray();
        if (missing.Length > 0)
        {
            return new ApplyResult(ApplyOutcome.Blocked, "Confirme os avisos antes de aplicar.", device, null);
        }

        if (plan.IsNoOp)
        {
            return new ApplyResult(ApplyOutcome.NothingToDo, "Essa taxa já está configurada.", device, null);
        }

        var backup = OverclockBackup.Capture(facts, DateTimeOffset.Now);
        Directory.CreateDirectory(BackupDirectory);
        var backupPath = Path.Combine(BackupDirectory, backup.FileName);
        await File.WriteAllTextAsync(backupPath, backup.ToJson());
        progress.Report($"Backup salvo em {backupPath}");

        try
        {
            progress.Report("Gravando configuração do hidusbf...");
            Write(instanceId, plan.NewLowerFilters, plan.Target.RegistryBInterval);

            progress.Report("Reiniciando o controle...");
            if (Restart(instanceId))
            {
                return new ApplyResult(ApplyOutcome.AppliedNeedsReboot, "Configuração gravada. O Windows pediu reinicialização do PC para concluir.", EdgeUsbDevices.Refresh(instanceId), backupPath);
            }

            if (await WaitForStartAsync(instanceId))
            {
                return new ApplyResult(ApplyOutcome.Applied, $"Taxa aplicada: {plan.Target.Label}.", EdgeUsbDevices.Refresh(instanceId), backupPath);
            }

            progress.Report("O controle não voltou a funcionar. Restaurando a configuração anterior...");
        }
        catch (Exception error)
        {
            progress.Report($"Erro: {error.Message}. Restaurando a configuração anterior...");
        }

        return await RollBackAsync(backup, backupPath, progress);
    }

    private static async Task<ApplyResult> RollBackAsync(OverclockBackup backup, string backupPath, IProgress<string> progress)
    {
        try
        {
            Write(backup.InstanceId, backup.LowerFilters, backup.StoredBInterval);
            var needsReboot = Restart(backup.InstanceId);
            if (needsReboot || await WaitForStartAsync(backup.InstanceId))
            {
                return new ApplyResult(ApplyOutcome.RolledBack, "A alteração foi desfeita e a configuração anterior foi restaurada.", EdgeUsbDevices.Refresh(backup.InstanceId), backupPath);
            }
        }
        catch (Exception error)
        {
            progress.Report($"Erro ao restaurar: {error.Message}");
        }

        return new ApplyResult(
            ApplyOutcome.RollbackFailed,
            "A configuração anterior foi regravada, mas o controle ainda não respondeu. Desconecte e reconecte o cabo; se persistir, reinicie o PC.",
            EdgeUsbDevices.Refresh(backup.InstanceId),
            backupPath);
    }

    private static void Write(string instanceId, IReadOnlyList<string> lowerFilters, int? bInterval)
    {
        var (set, data) = DeviceInfoSet.Open(instanceId);
        using (set)
        {
            using (var key = set.OpenDriverKey(ref data, writable: true))
            {
                if (bInterval is { } value)
                {
                    key.SetValue("bInterval", value, Microsoft.Win32.RegistryValueKind.DWord);
                }
                else
                {
                    key.DeleteValue("bInterval", throwOnMissingValue: false);
                }
            }

            set.SetMultiStringProperty(ref data, SpdrpLowerFilters, lowerFilters);
        }
    }

    private static bool Restart(string instanceId)
    {
        var (set, data) = DeviceInfoSet.Open(instanceId);
        using (set)
        {
            return set.RestartDevice(ref data);
        }
    }

    private static async Task<bool> WaitForStartAsync(string instanceId)
    {
        var deadline = DateTime.UtcNow + StartTimeout;
        while (DateTime.UtcNow < deadline)
        {
            await Task.Delay(250);
            if (ConfigManager.Locate(instanceId) is { } devInst
                && ConfigManager.Status(devInst) is { } status
                && (status.Status & DnStarted) != 0
                && (status.Status & DnHasProblem) == 0)
            {
                return true;
            }
        }

        return false;
    }
}
