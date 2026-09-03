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
            CheckForUpdatesOnStartup();
        }

        private void CheckForUpdatesOnStartup()
        {
            Task.Factory.StartNew(new Action(() =>
            {
                ReleaseInfo release = null;
                try { release = GitHubUpdater.CheckLatest(); }
                catch { return; }

                if (release == null)
                    return;

                var localVersion = GitHubUpdater.GetLocalVersion(_installDir);
                if (release.Version <= localVersion)
                    return;

                var asset = release.Assets.FirstOrDefault(
                    a => a.Name.Equals("DantesInfernoInstaller.exe",
                        StringComparison.OrdinalIgnoreCase));
                if (asset == null)
                    return;

                Dispatcher.Invoke(new Action(() =>
                {
                    _pendingUpdate = release;
                    DownloadUpdateButton.Visibility = Visibility.Visible;
                    UpdateStatusText.Text =
                        $"Update available: {release.TagName} (you have {localVersion})\n\n" +
                        $"{release.Name}\n\nClick \"Download & Install\" to update.";

                    var result = MessageBox.Show(this,
                        $"A new version is available: {release.TagName}\n" +
                        $"You currently have: {localVersion}\n\n" +
                        $"{release.Name}\n\n" +
                        "Would you like to download and install the update now?",
                        "Update Available",
                        MessageBoxButton.YesNo, MessageBoxImage.Question);

                    if (result == MessageBoxResult.Yes)
                    {
                        MainTabControl.SelectedIndex = 2;
                        DownloadUpdate_Click(null, null);
                    }
                }));
            }));
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
            var version = GitHubUpdater.GetLocalVersion(_installDir);
            VersionText.Text = "Version: " + version.ToString();
            UpdateVersionText.Text = "Installed version: " + version.ToString();

            ResScaleCombo.ItemsSource = new List<string>
            {
                "Original (720p)",
                "2x (1440p)",
                "3x (2160p / 4K)"
            };
            int scale = _config.ResolutionScale;
            if (scale < 1) scale = 1;
            if (scale > 3) scale = 3;
            ResScaleCombo.SelectedIndex = scale - 1;

            AAModeCombo.ItemsSource = new List<string> { "Off", "FXAA", "FXAA Extreme" };
            switch (_config.SwapPostEffect)
            {
                case "none": AAModeCombo.SelectedIndex = 0; break;
                case "fxaa": AAModeCombo.SelectedIndex = 1; break;
                case "fxaa_extreme": AAModeCombo.SelectedIndex = 2; break;
                default: AAModeCombo.SelectedIndex = 0; break;
            }

            AnisoCombo.ItemsSource = new List<string> { "Default", "1x", "2x", "4x", "8x", "16x" };
            int aniso = _config.AnisotropicOverride;
            if (aniso < 0) aniso = 0;
            else aniso = Array.IndexOf(new[] { 0, 1, 2, 4, 8, 16 }, aniso);
            if (aniso < 0) aniso = 0;
            AnisoCombo.SelectedIndex = aniso;

            FullscreenCheck.IsChecked = _config.Fullscreen;

            ControllerFixCheck.IsChecked = _config.InputBackend.Equals("sdl", StringComparison.OrdinalIgnoreCase);

            GlyphFamilyCombo.SelectedIndex = _config.GlyphFamily.Equals("playstation", StringComparison.OrdinalIgnoreCase) ? 1 : 0;

            LoggingEnabledCheck.IsChecked = !_config.LogLevel.Equals("off", StringComparison.OrdinalIgnoreCase);
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

        private void SaveSettingsToConfig()
        {
            int scaleIdx = ResScaleCombo.SelectedIndex;
            if (scaleIdx < 0) scaleIdx = 0;
            _config.ResolutionScale = scaleIdx + 1;

            int aaIdx = AAModeCombo.SelectedIndex;
            switch (aaIdx)
            {
                case 1: _config.SwapPostEffect = "fxaa"; break;
                case 2: _config.SwapPostEffect = "fxaa_extreme"; break;
                default: _config.SwapPostEffect = "none"; break;
            }

            int anisoIdx = AnisoCombo.SelectedIndex;
            if (anisoIdx <= 0)
                _config.AnisotropicOverride = -1;
            else
            {
                int[] anisoValues = { 0, 1, 2, 4, 8, 16 };
                _config.AnisotropicOverride = anisoValues[anisoIdx];
            }

            _config.Fullscreen = FullscreenCheck.IsChecked ?? true;

            _config.InputBackend = (ControllerFixCheck.IsChecked ?? false) ? "sdl" : "xinput";

            _config.GlyphFamily = GlyphFamilyCombo.SelectedIndex == 1 ? "playstation" : "xbox";

            bool loggingEnabled = LoggingEnabledCheck.IsChecked ?? true;
            _config.LogLevel = loggingEnabled ? "info" : "off";
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

            SaveSettingsToConfig();
            _config.Save();

            bool loggingEnabled = !_config.LogLevel.Equals("off", StringComparison.OrdinalIgnoreCase);

            ClearOldLogs();

            var args = new List<string>();
            args.Add(string.Format("--game_data_root=\"{0}\"", gameData));

            args.Add("--render_target_path_d3d12=rov");

            int scale = _config.ResolutionScale;
            if (scale > 1)
                args.Add(string.Format("--resolution_scale={0}", scale));

            if (!string.IsNullOrEmpty(_config.SwapPostEffect) && _config.SwapPostEffect != "none")
                args.Add(string.Format("--swap_post_effect={0}", _config.SwapPostEffect));

            if (_config.AnisotropicOverride >= 0)
                args.Add(string.Format("--anisotropic_override={0}", _config.AnisotropicOverride));

            args.Add("--vsync=true");
            args.Add("--d3d12_host_vsync=true");
            args.Add("--video_mode_refresh_rate=60");

            args.Add("--input_backend=" + _config.InputBackend);

            args.Add(loggingEnabled ? "--log_level=info" : "--log_level=off");

            if (_config.GlyphFamily.Equals("playstation", StringComparison.OrdinalIgnoreCase))
                args.Add("--glyph_family=playstation");

            string arguments = string.Join(" ", args);
            PlayNoteText.Text = "Launching with " + (scale > 1 ? scale + "x resolution" : "original resolution") + "...";
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
            _config.ResolutionScale = 2;
            _config.SwapPostEffect = "fxaa";
            _config.AnisotropicOverride = -1;
            _config.VSync = true;
            _config.Fullscreen = true;
            _config.InputBackend = "sdl";
            PopulateControls();
            MessageBox.Show("Recommended settings applied. Click Save Settings to keep them.", "Recommended",
                MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private void SaveSettings_Click(object sender, RoutedEventArgs e)
        {
            SaveSettingsToConfig();
            _config.Save();
            RefreshPlayStatus();
            MessageBox.Show("Settings saved. They will be applied when you click PLAY.", "Saved",
                MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private ReleaseInfo _pendingUpdate;

        private void CheckUpdates_Click(object sender, RoutedEventArgs e)
        {
            UpdateStatusText.Text = "Checking for updates...";
            DownloadUpdateButton.Visibility = Visibility.Collapsed;
            try
            {
                var release = GitHubUpdater.CheckLatest();
                var localVersion = GitHubUpdater.GetLocalVersion(_installDir);
                if (release.Version > localVersion)
                {
                    var asset = release.Assets.FirstOrDefault(
                        a => a.Name.Equals("DantesInfernoInstaller.exe",
                            StringComparison.OrdinalIgnoreCase));

                    if (asset != null)
                    {
                        _pendingUpdate = release;
                        DownloadUpdateButton.Visibility = Visibility.Visible;
                        UpdateStatusText.Text =
                            $"Update available!\nVersion: {release.TagName}\nName: {release.Name}\n\n" +
                            $"{release.Body}\n\nClick \"Download & Install\" to get the new installer.";
                    }
                    else
                    {
                        UpdateStatusText.Text =
                            $"Update available!\nVersion: {release.TagName}\nName: {release.Name}\n\n" +
                            $"{release.Body}\n\nNo installer asset found in this release. " +
                            "Visit the releases page to download manually:\n" +
                            release.HtmlUrl;
                    }
                }
                else
                {
                    _pendingUpdate = null;
                    UpdateStatusText.Text = $"You are up to date.\nLatest: {release.TagName}\nInstalled: {localVersion}";
                }
            }
            catch (Exception ex)
            {
                _pendingUpdate = null;
                UpdateStatusText.Text = "Failed to check for updates:\n" + ex.Message;
            }
        }

        private void DownloadUpdate_Click(object sender, RoutedEventArgs e)
        {
            if (_pendingUpdate == null)
            {
                MessageBox.Show("No update has been checked yet. Click \"Check for Updates\" first.",
                    "No Update", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            var asset = _pendingUpdate.Assets.FirstOrDefault(
                a => a.Name.Equals("DantesInfernoInstaller.exe",
                    StringComparison.OrdinalIgnoreCase));
            if (asset == null)
            {
                MessageBox.Show("The latest release has no installer asset to download.",
                    "No Installer", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            var confirm = MessageBox.Show(
                $"A new version ({_pendingUpdate.TagName}) is available.\n\n" +
                "The installer will be downloaded and launched. " +
                "The launcher will close so the installer can update your game files.\n\n" +
                "Continue?",
                "Download and Install Update",
                MessageBoxButton.YesNo, MessageBoxImage.Question);
            if (confirm != MessageBoxResult.Yes)
                return;

            DownloadUpdateButton.IsEnabled = false;
            CheckUpdatesButton.IsEnabled = false;
            DownloadProgress.Visibility = Visibility.Visible;
            DownloadProgress.Value = 0;
            UpdateStatusText.Text = "Downloading installer...";

            string destDir = Path.Combine(Path.GetTempPath(), "DantesInfernoUpdate");

            Task.Factory.StartNew(new Action(() =>
            {
                string downloadedPath = null;
                string errorMsg = null;
                try
                {
                    downloadedPath = GitHubUpdater.DownloadAsset(asset, destDir,
                        (received, total) =>
                        {
                            if (total > 0)
                            {
                                int pct = (int)(100L * received / total);
                                Dispatcher.Invoke(new Action(() =>
                                {
                                    DownloadProgress.Value = pct;
                                    UpdateStatusText.Text =
                                        $"Downloading... {pct}% ({received / 1024 / 1024} MB / {total / 1024 / 1024} MB)";
                                }));
                            }
                        });
                }
                catch (Exception ex)
                {
                    errorMsg = ex.Message;
                }

                Dispatcher.Invoke(new Action(() =>
                {
                    DownloadProgress.Value = 100;
                    DownloadUpdateButton.IsEnabled = true;
                    CheckUpdatesButton.IsEnabled = true;

                    if (errorMsg != null)
                    {
                        DownloadProgress.Visibility = Visibility.Collapsed;
                        UpdateStatusText.Text = "Download failed:\n" + errorMsg;
                        return;
                    }

                    UpdateStatusText.Text = "Download complete. Launching installer...";

                    var launch = MessageBox.Show(
                        "The installer has been downloaded. Click OK to launch it.\n" +
                        "The launcher will close and the installer will guide you through the update.",
                        "Launch Installer", MessageBoxButton.OKCancel, MessageBoxImage.Information);

                    if (launch != MessageBoxResult.OK)
                    {
                        DownloadProgress.Visibility = Visibility.Collapsed;
                        UpdateStatusText.Text = "Installer downloaded to:\n" + downloadedPath +
                            "\n\nYou can run it manually later.";
                        return;
                    }

                    try
                    {
                        Process.Start(new ProcessStartInfo
                        {
                            FileName = downloadedPath,
                            UseShellExecute = true,
                        });
                        Application.Current.Shutdown();
                    }
                    catch (Exception ex)
                    {
                        DownloadProgress.Visibility = Visibility.Collapsed;
                        UpdateStatusText.Text = "Failed to launch installer:\n" + ex.Message +
                            "\n\nYou can run it manually from:\n" + downloadedPath;
                    }
                }));
            }));
        }

        private void SupportButton_Click(object sender, RoutedEventArgs e)
        {
            Process.Start(new ProcessStartInfo("https://ko-fi.com/zerkiller") { UseShellExecute = true });
        }
    }
}
