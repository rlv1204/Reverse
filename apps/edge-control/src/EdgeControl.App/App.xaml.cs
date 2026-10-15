using System.Windows;
using System.Windows.Threading;

namespace EdgeControl.App;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += OnUnhandled;
        base.OnStartup(e);
        new MainWindow().Show();
    }

    private static void OnUnhandled(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        MessageBox.Show(e.Exception.Message, "Edge Control", MessageBoxButton.OK, MessageBoxImage.Error);
        e.Handled = true;
    }
}
