using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media.Imaging;

namespace DantesInferno.Launcher
{
    public partial class MainWindow : Window
    {
        private GameConfig _config;
        private string _installDir;
        private bool _gameRunning;

        public MainWindow()
        {
            InitializeComponent();
            InitializeTheme();
            LoadConfiguration();
            PopulateControls();
            RefreshPlayStatus();
        }

        private void InitializeTheme()
        {
            try
            {
                string iconPath = Path.Combine(_installDir ?? PathHelper.ExecutableDirectory, "icon.ico");
                if (File.Exists(iconPath))
                    this.Icon = BitmapFrame.Create(new Uri(iconPath, UriKind.Absolute));

                string bannerPath = Path.Combine(_installDir ?? PathHelper.ExecutableDirectory, "banner.jpg");
                if (File.Exists(bannerPath))
                    BannerImage.Source = new BitmapImage(new Uri(bannerPath, UriKind.Absolute));
            }
            catch { }
        }

        private void LoadConfiguration()
        {
            _installDir = PathHelper.ExecutableDirectory;
            string configPath = PathHelper.GetGameConfigPath(_installDir);
            _config = GameConfig.Load(configPath);

            if (string.IsNullOrWhiteSpace(_config.GameDataRoot))
                _config.GameDataRoot = PathHelper.GetGameDataPath(_installDir);
        }

        private void PopulateControls()
        {
            VersionText.Text = "Version: " + GitHubUpdater.GetLocalVersion(_installDir);
            UpdateVersionText.Text = "Installed version: " + GitHubUpdater.GetLocalVersion(_installDir);

            ResolutionCombo.ItemsSource = new List<string> { "720p", "1080p", "1440p", "4k", "2560x1080", "3440x1440" };
            ResolutionCombo.SelectedItem = _config.Resolution ?? "1080p";

            FrameCapCombo.ItemsSource = new List<string> { "60 Hz (VSync On)", "120 Hz (VSync On)", "Unlimited (VSync Off)" };
            FrameCapCombo.SelectedIndex = (int)_config.FrameCap;

            AnisoCombo.ItemsSource = new List<string> { "No override (-1)", "Off (0)", "1x", "2x", "4x", "8x", "16x" };
            AnisoCombo.SelectedIndex = _config.AnisotropicOverride + 1;

            AAModeCombo.ItemsSource = new List<string> { "None", "FXAA", "FXAA Extreme" };
            switch (_config.SwapPostEffect)
            {
                case "none": AAModeCombo.SelectedIndex = 0; break;
                case "fxaa": AAModeCombo.SelectedIndex = 1; break;
                case "fxaa_extreme": AAModeCombo.SelectedIndex = 2; break;
                default: AAModeCombo.SelectedIndex = 0; break;
            }

            MsaaCheck.IsChecked = _config.Native2xMsaa;
            FullscreenCheck.IsChecked = _config.Fullscreen;

            ResScaleCombo.ItemsSource = new List<string> { "1x", "2x", "3x", "4x", "5x", "6x", "7x", "8x" };
            ResScaleCombo.SelectedIndex = _config.ResolutionScale - 1;

            ControllerFixCheck.IsChecked = _config.InputBackend.Equals("sdl", StringComparison.OrdinalIgnoreCase);
            SharpenCheck.IsChecked = _config.AnisotropicOverride == 5 && _config.SwapPostEffect == "fxaa_extreme";
            CommonFixesCheck.IsChecked = _config.RenderTargetPath.Equals("rov", StringComparison.OrdinalIgnoreCase);
        }

        private void RefreshPlayStatus()
        {
            string exePath = PathHelper.GetGameExecutablePath(_installDir);
            string gameData = _config.GameDataRoot ?? PathHelper.GetGameDataPath(_installDir);
            if (File.Exists(exePath) && Directory.Exists(gameData))
                PlayStatusText.Text = "Game files found.";
            else
                PlayStatusText.Text = "Game files missing. Run the installer first.";
        }

        private void ClearOldLogs()
        {
            try
            {
                string logsDir = PathHelper.GetLogsPath(_installDir);
                if (!Directory.Exists(logsDir))
                    return;

                foreach (var file in Directory.GetFiles(logsDir, "*.log", SearchOption.AllDirectories))
                {
                    try { File.Delete(file); } catch { }
                }
            }
            catch { }
        }

        private void PlayButton_Click(object sender, RoutedEventArgs e)
        {
            if (_gameRunning)
            {
                MessageBox.Show("The game is already running.", "Already Running", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            string exePath = PathHelper.GetGameExecutablePath(_installDir);
            if (!File.Exists(exePath))
            {
                MessageBox.Show("dantes_inferno.exe was not found in the install directory.", "Missing Game", MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }

            string gameData = _config.GameDataRoot ?? PathHelper.GetGameDataPath(_installDir);
            if (!Directory.Exists(gameData))
            {
                MessageBox.Show("Game data folder was not found: " + gameData, "Missing Data", MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }

            bool loggingEnabled = LoggingEnabledCheck.IsChecked ?? true;

            ClearOldLogs();

            var args = new List<string>();
            args.Add(string.Format("--game_data_root=\"{0}\"", gameData));
            args.Add("--render_target_path_d3d12=rov");
            args.Add(loggingEnabled ? "--log_level=info" : "--log_level=off");

            string arguments = string.Join(" ", args);
            PlayNoteText.Text = "Launch command: dantes_inferno.exe " + arguments;
            PlayButton.IsEnabled = false;
            _gameRunning = true;

            Task.Factory.StartNew(new Action(() =>
            {
                int exitCode = -1;
                try
                {
                    var psi = new ProcessStartInfo
                    {
                        FileName = exePath,
                        Arguments = arguments,
                        WorkingDirectory = _installDir,
                        UseShellExecute = false,
                    };

                    using (var process = Process.Start(psi))
                    {
                        process.WaitForExit();
                        exitCode = process.ExitCode;
                    }
                }
                catch (Exception ex)
                {
                    Dispatcher.Invoke(new Action(() =>
                    {
                        MessageBox.Show("Failed to start the game:\n" + ex.Message, "Launch Error", MessageBoxButton.OK, MessageBoxImage.Error);
                    }));
                }

                Dispatcher.Invoke(new Action(() =>
                {
                    _gameRunning = false;
                    PlayButton.IsEnabled = true;

                    if (exitCode != 0)
                        ShowCrashDialog(exitCode);
                }));
            }));
        }

        private void ShowCrashDialog(int exitCode)
        {
            string logsDir = PathHelper.GetLogsPath(_installDir);
            string latestLog = null;

            try
            {
                if (Directory.Exists(logsDir))
                {
                    var logFile = Directory.GetFiles(logsDir, "*.log", SearchOption.AllDirectories)
                        .OrderByDescending(f => File.GetLastWriteTime(f))
                        .FirstOrDefault();
                    if (logFile != null)
                        latestLog = logFile;
                }
            }
            catch { }

            string message = "Dante's Inferno has crashed (exit code: " + exitCode + ").\n\n";
            if (latestLog != null)
                message += "Log file: " + latestLog + "\n\n";
            else
                message += "No log file was found in " + logsDir + "\n\n";
            message += "Please report this on GitHub and attach the log file.\n";
            message += "https://github.com/florinp93/dantes-inferno/issues\n\n";
            message += "Click OK to open the log folder and the GitHub issues page.";

            var result = MessageBox.Show(message, "Game Crashed", MessageBoxButton.OKCancel, MessageBoxImage.Error);
            if (result == MessageBoxResult.OK)
            {
                try
                {
                    if (Directory.Exists(logsDir))
                        Process.Start(new ProcessStartInfo("explorer.exe", "\"" + logsDir + "\"") { UseShellExecute = true });
                    else
                        Process.Start(new ProcessStartInfo("explorer.exe", "\"" + _installDir + "\"") { UseShellExecute = true });
                }
                catch { }

                try
                {
                    Process.Start(new ProcessStartInfo("https://github.com/florinp93/dantes-inferno/issues") { UseShellExecute = true });
                }
                catch { }
            }
        }

        private void ExitButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        private void ApplyRecommended_Click(object sender, RoutedEventArgs e)
        {
            _config.Resolution = "1080p";
            _config.AnisotropicOverride = -1;
            _config.SwapPostEffect = "none";
            _config.VSync = true;
            _config.Native2xMsaa = false;
            _config.Fullscreen = true;
            _config.RenderTargetPath = "rov";
            _config.ResolutionScale = 1;
            _config.InputBackend = "sdl";
            AutoOptimizationsCheck.IsChecked = true;
            PopulateControls();
        }

        private void SaveSettings_Click(object sender, RoutedEventArgs e)
        {
            _config.Save();
            RefreshPlayStatus();
            MessageBox.Show("Settings saved to dantes_inferno.toml.", "Saved", MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private void CheckUpdates_Click(object sender, RoutedEventArgs e)
        {
            UpdateStatusText.Text = "Checking for updates...";
            try
            {
                var release = GitHubUpdater.CheckLatest();
                var localVersion = GitHubUpdater.GetLocalVersion(_installDir);
                if (release.Version > localVersion)
                {
                    string assetInfo = "";
                    var asset = release.Assets.FirstOrDefault(a => a.Name.Equals("DantesInfernoInstaller.exe", StringComparison.OrdinalIgnoreCase));
                    if (asset != null)
                    {
                        assetInfo = $"\n\nDownload: {asset.BrowserDownloadUrl}";
                    }
                    UpdateStatusText.Text = $"Update available!\nVersion: {release.TagName}\nName: {release.Name}\n\n{release.Body}{assetInfo}";
                }
                else
                {
                    UpdateStatusText.Text = $"You are up to date.\nLatest: {release.TagName}\nInstalled: {localVersion}";
                }
            }
            catch (Exception ex)
            {
                UpdateStatusText.Text = "Failed to check for updates:\n" + ex.Message;
            }
        }

        private void SupportButton_Click(object sender, RoutedEventArgs e)
        {
            Process.Start(new ProcessStartInfo("https://ko-fi.com/zerkiller") { UseShellExecute = true });
        }
    }
}
