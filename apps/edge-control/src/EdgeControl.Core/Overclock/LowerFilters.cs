namespace EdgeControl.Core.Overclock;

/// <summary>
/// Edits the device LowerFilters list the same way the hidusbf setup does:
/// enabling inserts "hidusbf" at the head only when absent; disabling removes
/// every case-insensitive occurrence. Other filters keep their order.
/// </summary>
public static class LowerFilters
{
    public const string HidUsbfService = "hidusbf";

    public static bool Contains(IReadOnlyList<string> filters) =>
        filters.Any(f => string.Equals(f, HidUsbfService, StringComparison.OrdinalIgnoreCase));

    public static IReadOnlyList<string> WithHidUsbf(IReadOnlyList<string> filters, bool enabled)
    {
        if (enabled)
        {
            return Contains(filters) ? filters.ToArray() : [HidUsbfService, .. filters];
        }

        return filters
            .Where(f => !string.Equals(f, HidUsbfService, StringComparison.OrdinalIgnoreCase))
            .ToArray();
    }
}
