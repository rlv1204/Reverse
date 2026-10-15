using System.Security.Principal;
using System.Windows.Threading;
using EdgeControl.App.Services;

namespace EdgeControl.App.ViewModels;

public sealed class NavItem
{
    public required string Title { get; init; }
    public required string Glyph { get; init; }
    public required PageViewModel Page { get; init; }
}

public abstract class PageViewModel : ObservableObject
{
    /// <summary>Called about 30 times per second while the page is visible.</summary>
    public virtual void Tick()
    {
    }

    public virtual void OnShown()
    {
    }
}

public sealed class MainViewModel : ObservableObject, IDisposable
{
    private readonly DispatcherTimer _uiTimer;
    private readonly DispatcherTimer _connectTimer;
    private readonly OverclockViewModel _overclock;
    private NavItem _selected;
    private string _connectionText = "Procurando controle...";
    private bool _isConnected;

    public MainViewModel()
    {
        Session = new ControllerSession();
        IsElevated = new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator);

        var overclock = _overclock = new OverclockViewModel(Session, IsElevated);
        Home = new HomeViewModel(Session, overclock);
        Items =
        [
            new NavItem { Title = "Controle", Glyph = "", Page = Home },
            new NavItem { Title = "Teste de entradas", Glyph = "", Page = new InputTestViewModel(Session) },
            new NavItem { Title = "Perfis", Glyph = "", Page = new ProfilesViewModel() },
            new NavItem { Title = "Overclock USB", Glyph = "", Page = overclock },
            new NavItem { Title = "Segurança e sobre", Glyph = "", Page = new AboutViewModel() },
        ];
        _selected = Items[0];

        _uiTimer = new DispatcherTimer(TimeSpan.FromMilliseconds(33), DispatcherPriority.Render, (_, _) => OnUiTick(), Dispatcher.CurrentDispatcher);
        _connectTimer = new DispatcherTimer(TimeSpan.FromSeconds(2), DispatcherPriority.Background, (_, _) => OnConnectTick(), Dispatcher.CurrentDispatcher);
        OnConnectTick();
        _selected.Page.OnShown();
        _uiTimer.Start();
        _connectTimer.Start();
    }

    public ControllerSession Session { get; }
    public HomeViewModel Home { get; }
    public IReadOnlyList<NavItem> Items { get; }
    public bool IsElevated { get; }

    public NavItem Selected
    {
        get => _selected;
        set
        {
            if (Set(ref _selected, value))
            {
                value.Page.OnShown();
            }
        }
    }

    public string ConnectionText
    {
        get => _connectionText;
        private set => Set(ref _connectionText, value);
    }

    public bool IsConnected
    {
        get => _isConnected;
        private set => Set(ref _isConnected, value);
    }

    private void OnConnectTick()
    {
        Session.EnsureConnected();
        var connected = Session.Kind == ConnectionKind.Usb;
        if (connected != IsConnected && !_overclock.Busy)
        {
            // Plug, unplug or restart: re-read the USB node so the overclock data is current.
            _overclock.Refresh();
        }

        IsConnected = connected;
        ConnectionText = Session.Kind switch
        {
            ConnectionKind.Usb => "DualSense Edge · USB",
            ConnectionKind.Bluetooth => "Conectado por Bluetooth · conecte o cabo USB",
            _ => Session.LastError ?? "Nenhum controle conectado",
        };
    }

    private void OnUiTick() => Selected.Page.Tick();

    public void Dispose()
    {
        _uiTimer.Stop();
        _connectTimer.Stop();
        Session.Dispose();
    }
}
