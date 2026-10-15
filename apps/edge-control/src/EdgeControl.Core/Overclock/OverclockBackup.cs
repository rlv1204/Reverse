using System.Text.Json;

namespace EdgeControl.Core.Overclock;

/// <summary>
/// The exact pre-change values of the two registry entries this app writes.
/// Saved before every change and used to roll back automatically when the
/// controller does not come back after a restart.
/// </summary>
public sealed record OverclockBackup(
    string InstanceId,
    IReadOnlyList<string> LowerFilters,
    int? StoredBInterval,
    DateTimeOffset CreatedAt)
{
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };

    public static OverclockBackup Capture(OverclockFacts facts, DateTimeOffset now) =>
        new(facts.InstanceId, facts.LowerFilters.ToArray(), facts.StoredBInterval, now);

    public string ToJson() => JsonSerializer.Serialize(this, Options);

    public static OverclockBackup? FromJson(string json) =>
        JsonSerializer.Deserialize<OverclockBackup>(json, Options);

    public string FileName => $"backup-{CreatedAt.UtcDateTime:yyyyMMdd-HHmmss}.json";
}
