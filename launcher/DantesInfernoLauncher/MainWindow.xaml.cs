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
            var version = GitHubUpdater.GetLocalVersion(_installDir);
            VersionText.Text = "Version: " + version.ToString();
            UpdateVersionText.Text = "Installed version: " + version.ToString();

            // Resolution scale — the main quality setting
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

            // Anti-aliasing
            AAModeCombo.ItemsSource = new List<string> { "Off", "FXAA", "FXAA Extreme" };
            switch (_config.SwapPostEffect)
            {
                case "none": AAModeCombo.SelectedIndex = 0; break;
                case "fxaa": AAModeCombo.SelectedIndex = 1; break;
                case "fxaa_extreme": AAModeCombo.SelectedIndex = 2; break;
                default: AAModeCombo.SelectedIndex = 0; break;
            }

            // Texture filtering
            AnisoCombo.ItemsSource = new List<string> { "Default", "1x", "2x", "4x", "8x", "16x" };
            int aniso = _config.AnisotropicOverride;
            if (aniso < 0) aniso = 0;       // Default
            else if (aniso == 0) aniso = 0;  // Off maps to Default in UI
            else aniso = Array.IndexOf(new[] { 0, 1, 2, 4, 8, 16 }, aniso);
            if (aniso < 0) aniso = 0;
            AnisoCombo.SelectedIndex = aniso;

            // Fullscreen
            FullscreenCheck.IsChecked = _config.Fullscreen;

            // Controller
            ControllerFixCheck.IsChecked = _config.InputBackend.Equals("sdl", StringComparison.OrdinalIgnoreCase);

            PlayStationGlyphsCheck.IsChecked = _config.PlayStationGlyphs;
            GlyphFamilyCombo.SelectedIndex = _config.PlayStationGlyphs ? 1 : 0;

            // Logging
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
            // Resolution scale
            int scaleIdx = ResScaleCombo.SelectedIndex;
            if (scaleIdx < 0) scaleIdx = 0;
            _config.ResolutionScale = scaleIdx + 1;

            // Anti-aliasing
            int aaIdx = AAModeCombo.SelectedIndex;
            switch (aaIdx)
            {
                case 1: _config.SwapPostEffect = "fxaa"; break;
                case 2: _config.SwapPostEffect = "fxaa_extreme"; break;
                default: _config.SwapPostEffect = "none"; break;
            }

            // Texture filtering
            int anisoIdx = AnisoCombo.SelectedIndex;
            if (anisoIdx <= 0)
                _config.AnisotropicOverride = -1; // Default
            else
            {
                int[] anisoValues = { 0, 1, 2, 4, 8, 16 };
                _config.AnisotropicOverride = anisoValues[anisoIdx];
            }

            // Fullscreen
            _config.Fullscreen = FullscreenCheck.IsChecked ?? true;

            // Controller
            _config.InputBackend = (ControllerFixCheck.IsChecked ?? false) ? "sdl" : "none";

            _config.PlayStationGlyphs = GlyphFamilyCombo.SelectedIndex == 1;

            // Logging
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

            // Save settings before launching (silently, no dialog)
            SaveSettingsToConfig();
            _config.Save();

            bool loggingEnabled = !_config.LogLevel.Equals("off", StringComparison.OrdinalIgnoreCase);

            ClearOldLogs();

            var args = new List<string>();
            args.Add(string.Format("--game_data_root=\"{0}\"", gameData));

            // Use ROV (rasterizer-ordered views) for correct alpha/transparency
            // rendering. The host RTV path has known issues with alpha-blended
            // models (e.g. invisible characters).
            args.Add("--render_target_path_d3d12=rov");

            // Resolution scale
            int scale = _config.ResolutionScale;
            if (scale > 1)
                args.Add(string.Format("--resolution_scale={0}", scale));

            // Anti-aliasing
            if (!string.IsNullOrEmpty(_config.SwapPostEffect) && _config.SwapPostEffect != "none")
                args.Add(string.Format("--swap_post_effect={0}", _config.SwapPostEffect));

            // Anisotropic override
            if (_config.AnisotropicOverride >= 0)
                args.Add(string.Format("--anisotropic_override={0}", _config.AnisotropicOverride));

            // VSync — game runs at hardcoded 60 FPS.
            // Always enable host VSync for smooth, tear-free frame pacing.
            args.Add("--vsync=true");
            args.Add("--d3d12_host_vsync=true");
            args.Add("--video_mode_refresh_rate=60");

            // Input
            if (_config.InputBackend.Equals("sdl", StringComparison.OrdinalIgnoreCase))
                args.Add("--input_backend=sdl");

            // Logging
            args.Add(loggingEnabled ? "--log_level=info" : "--log_level=off");

            if (GlyphFamilyCombo.SelectedIndex == 1)
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
