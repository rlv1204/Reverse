namespace EdgeControl.App.ViewModels;

/// <summary>
/// Placeholder until the PlayStation Accessories protocol is recovered and
/// each command is verified. Nothing on this page writes to the controller.
/// </summary>
public sealed class ProfilesViewModel : PageViewModel
{
    public IReadOnlyList<string> Planned { get; } =
    [
        "Perfis personalizados gravados na memória do controle",
        "Remapeamento de botões, incluindo os botões traseiros",
        "Curvas e zonas mortas dos analógicos",
        "Curso e zona morta dos gatilhos",
        "Intensidade da vibração e dos gatilhos adaptáveis",
    ];
}

public sealed class AboutViewModel : PageViewModel
{
    public string Version { get; } =
        typeof(AboutViewModel).Assembly.GetName().Version?.ToString(3) ?? "0.0.0";
}
