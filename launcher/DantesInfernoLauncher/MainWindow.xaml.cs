using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace DantesInferno.Launcher
{
    public partial class MainWindow : Window
    {
        private GameConfig _config;
        private string _installDir;

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

                string logoPath = Path.Combine(_installDir ?? PathHelper.ExecutableDirectory, "icon.png");
                if (File.Exists(logoPath))
                    LogoImage.Source = new BitmapImage(new Uri(logoPath, UriKind.Absolute));
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
                default: AAModeCombo.SelectedIndex = 1; break;
            }

            MsaaCheck.IsChecked = _config.Native2xMsaa;
            FullscreenCheck.IsChecked = _config.Fullscreen;

            ResScaleCombo.ItemsSource = new List<string> { "1x", "2x", "3x", "4x", "5x", "6x", "7x", "8x" };
            ResScaleCombo.SelectedIndex = _config.ResolutionScale - 1;

            GameDataTextBox.Text = _config.GameDataRoot;

            ControllerFixCheck.IsChecked = _config.InputBackend.Equals("sdl", StringComparison.OrdinalIgnoreCase);
            SharpenCheck.IsChecked = false;
            CommonFixesCheck.IsChecked = _config.RenderTargetPath.Equals("rov", StringComparison.OrdinalIgnoreCase);
        }

        private void ApplySettingsToConfig()
        {
            _config.Resolution = ResolutionCombo.SelectedItem as string ?? "1080p";
            _config.FrameCap = (FrameCapOption)FrameCapCombo.SelectedIndex;
            _config.Fullscreen = FullscreenCheck.IsChecked ?? true;
            _config.Native2xMsaa = MsaaCheck.IsChecked ?? true;
            _config.ResolutionScale = ResScaleCombo.SelectedIndex + 1;
            _config.AnisotropicOverride = AnisoCombo.SelectedIndex - 1;

            string aa = AAModeCombo.SelectedIndex == 0 ? "none" : (AAModeCombo.SelectedIndex == 2 ? "fxaa_extreme" : "fxaa");
            _config.SwapPostEffect = aa;

            _config.GameDataRoot = GameDataTextBox.Text.Trim();
            _config.InputBackend = (ControllerFixCheck.IsChecked ?? true) ? "sdl" : "xinput";
            _config.RenderTargetPath = (CommonFixesCheck.IsChecked ?? true) ? "rov" : "";

            if (SharpenCheck.IsChecked ?? false)
            {
                _config.AnisotropicOverride = 5;
                _config.SwapPostEffect = "fxaa_extreme";
            }

            if (AutoOptimizationsCheck.IsChecked ?? false)
            {
                _config.Resolution = "1080p";
                _config.AnisotropicOverride = 5;
                _config.SwapPostEffect = "fxaa";
                _config.VSync = true;
                _config.Native2xMsaa = true;
                _config.Fullscreen = true;
                _config.RenderTargetPath = "rov";
            }
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

        private void PlayButton_Click(object sender, RoutedEventArgs e)
        {
            ApplySettingsToConfig();
            _config.Save();

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

            var psi = new ProcessStartInfo
            {
                FileName = exePath,
                Arguments = "--game_data_root=\"" + gameData + "\"",
                WorkingDirectory = _installDir,
                UseShellExecute = false,
            };

            try
            {
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to start the game:\n" + ex.Message, "Launch Error", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private void ExitButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        private void BrowseGameData_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new System.Windows.Forms.FolderBrowserDialog
            {
                Description = "Select the folder containing default.xex",
                SelectedPath = GameDataTextBox.Text
            };
            var result = dialog.ShowDialog();
            if (result == System.Windows.Forms.DialogResult.OK)
            {
                GameDataTextBox.Text = dialog.SelectedPath;
            }
        }

        private void ApplyRecommended_Click(object sender, RoutedEventArgs e)
        {
            _config.ApplyRecommendedPreset();
            AutoOptimizationsCheck.IsChecked = true;
            PopulateControls();
        }

        private void SaveSettings_Click(object sender, RoutedEventArgs e)
        {
            ApplySettingsToConfig();
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
                    var asset = release.Assets.FirstOrDefault(a => a.Name.Equals("dantes_inferno.zip", StringComparison.OrdinalIgnoreCase));
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
    }
}
