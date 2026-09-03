using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Windows;
using System.Windows.Media.Imaging;

namespace DantesInferno.Installer
{
    public partial class MainWindow : Window
    {
        private int _step = 1;
        private string _destination;
        private string _isoPath;
        private string _installerDir;
        private string _payloadDir;
        private readonly BackgroundWorker _worker = new BackgroundWorker();

        public MainWindow()
        {
            InitializeComponent();
            InitializeTheme();
            _installerDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            _payloadDir = ExtractEmbeddedPayload();
            UpdateNavigation();

            _worker.WorkerReportsProgress = true;
            _worker.WorkerSupportsCancellation = true;
            _worker.DoWork += Worker_DoWork;
            _worker.ProgressChanged += Worker_ProgressChanged;
            _worker.RunWorkerCompleted += Worker_RunWorkerCompleted;
        }

        private void InitializeTheme()
        {
            try
            {
                string iconPath = Path.Combine(_installerDir ?? Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location), "icon.ico");
                if (File.Exists(iconPath))
                    this.Icon = BitmapFrame.Create(new Uri(iconPath, UriKind.Absolute));
            }
            catch { }
        }

        private string ExtractEmbeddedPayload()
        {
            string exePath = Assembly.GetExecutingAssembly().Location;
            string marker = "DANTES_PAYLOAD";
            byte[] markerBytes = Encoding.ASCII.GetBytes(marker);
            int trailerSize = markerBytes.Length + sizeof(long);

            try
            {
                using (var stream = new FileStream(exePath, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    long length = stream.Length;
                    if (length < trailerSize)
                        return null;

                    stream.Seek(length - markerBytes.Length, SeekOrigin.Begin);
                    byte[] fileMarker = new byte[markerBytes.Length];
                    stream.Read(fileMarker, 0, fileMarker.Length);
                    if (!fileMarker.SequenceEqual(markerBytes))
                        return null;

                    stream.Seek(length - trailerSize, SeekOrigin.Begin);
                    byte[] sizeBytes = new byte[sizeof(long)];
                    stream.Read(sizeBytes, 0, sizeBytes.Length);
                    long payloadSize = BitConverter.ToInt64(sizeBytes, 0);

                    long payloadOffset = length - trailerSize - payloadSize;
                    if (payloadOffset < 0)
                        return null;

                    stream.Seek(payloadOffset, SeekOrigin.Begin);
                    byte[] payload = new byte[payloadSize];
                    stream.Read(payload, 0, payload.Length);

                    string tempRoot = Path.Combine(Path.GetTempPath(), "DantesInferno", Guid.NewGuid().ToString("N"));
                    Directory.CreateDirectory(tempRoot);
                    ExtractPayloadArchive(payload, tempRoot);
                    return tempRoot;
                }
            }
            catch (Exception)
            {
                return null;
            }
        }

        private void ExtractPayloadArchive(byte[] payload, string targetRoot)
        {
            using (var ms = new MemoryStream(payload))
            using (var reader = new BinaryReader(ms, Encoding.UTF8))
            {
                int count = reader.ReadInt32();
                for (int i = 0; i < count; i++)
                {
                    int pathLen = reader.ReadInt32();
                    byte[] pathBytes = reader.ReadBytes(pathLen);
                    string relativePath = Encoding.UTF8.GetString(pathBytes);
                    long fileLen = reader.ReadInt64();
                    byte[] fileBytes = reader.ReadBytes((int)fileLen);

                    string targetPath = Path.Combine(targetRoot, relativePath);
                    Directory.CreateDirectory(Path.GetDirectoryName(targetPath));
                    File.WriteAllBytes(targetPath, fileBytes);
                }
            }
        }

        private string GetPayloadFile(string relativePath)
        {
            if (!string.IsNullOrEmpty(_payloadDir))
            {
                string payloadFile = Path.Combine(_payloadDir, relativePath);
                if (File.Exists(payloadFile) || Directory.Exists(payloadFile))
                    return payloadFile;
            }
            return Path.Combine(_installerDir, relativePath);
        }

        private void UpdateNavigation()
        {
            Step1Welcome.Visibility = _step == 1 ? Visibility.Visible : Visibility.Collapsed;
            Step2Destination.Visibility = _step == 2 ? Visibility.Visible : Visibility.Collapsed;
            Step3Iso.Visibility = _step == 3 ? Visibility.Visible : Visibility.Collapsed;
            Step4Progress.Visibility = _step == 4 ? Visibility.Visible : Visibility.Collapsed;
            Step5Finish.Visibility = _step == 5 ? Visibility.Visible : Visibility.Collapsed;

            BackButton.IsEnabled = _step > 1 && _step < 5;
            NextButton.IsEnabled = _step != 4;
            NextButton.Content = _step == 3 ? "Install" : (_step == 5 ? "Finish" : "Next");
        }

        private void BackButton_Click(object sender, RoutedEventArgs e)
        {
            if (_step > 1 && _step < 5)
            {
                _step--;
                UpdateNavigation();
            }
        }

        private void NextButton_Click(object sender, RoutedEventArgs e)
        {
            if (_step == 3)
            {
                _destination = DestinationTextBox.Text.Trim();
                _isoPath = IsoTextBox.Text.Trim();

                if (string.IsNullOrWhiteSpace(_destination) || !Directory.Exists(Path.GetDirectoryName(_destination)))
                {
                    MessageBox.Show("Please choose a valid destination folder.", "Invalid Destination", MessageBoxButton.OK, MessageBoxImage.Warning);
                    return;
                }
                if (!File.Exists(_isoPath))
                {
                    MessageBox.Show("Please select a valid ISO file.", "Invalid ISO", MessageBoxButton.OK, MessageBoxImage.Warning);
                    return;
                }

                _step = 4;
                UpdateNavigation();
                InstallProgress.IsIndeterminate = true;
                _worker.RunWorkerAsync();
                return;
            }

            if (_step == 5)
            {
                if (CreateShortcutCheck.IsChecked == true)
                    CreateDesktopShortcut();
                Close();
                return;
            }

            if (_step < 4)
            {
                _step++;
                UpdateNavigation();
            }
        }

        private void BrowseDestination_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new System.Windows.Forms.FolderBrowserDialog
            {
                Description = "Select the installation folder",
                SelectedPath = DestinationTextBox.Text
            };
            if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                DestinationTextBox.Text = dialog.SelectedPath;
        }

        private void BrowseIso_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new System.Windows.Forms.OpenFileDialog
            {
                Filter = "Xbox ISO files (*.iso)|*.iso|All files (*.*)|*.*",
                Title = "Select Dante's Inferno ISO"
            };
            if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
                IsoTextBox.Text = dialog.FileName;
        }

        private void Worker_DoWork(object sender, DoWorkEventArgs e)
        {
            try
            {
                _worker.ReportProgress(0, "Preparing destination...");
                Directory.CreateDirectory(_destination);
                string gameDir = Path.Combine(_destination, "game");

                // Only extract the ISO if game data is not already present.
                bool needExtraction = !Directory.Exists(gameDir) ||
                    !Directory.GetFiles(gameDir, "default.xex", SearchOption.AllDirectories).Any();
                if (needExtraction)
                {
                    if (Directory.Exists(gameDir))
                    {
                        _worker.ReportProgress(5, "Removing old game data...");
                        try { Directory.Delete(gameDir, true); } catch { }
                    }

                    _worker.ReportProgress(10, "Extracting ISO to game folder (this may take a few minutes)...");
                    string extractExe = GetPayloadFile("extract-xiso.exe");
                    if (!File.Exists(extractExe))
                        throw new FileNotFoundException("extract-xiso.exe was not found in the installer payload.");

                    var psi = new ProcessStartInfo
                    {
                        FileName = extractExe,
                        Arguments = $"-x -d \"{gameDir}\" -s \"{_isoPath}\"",
                        WorkingDirectory = _destination,
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                    };

                    using (var process = Process.Start(psi))
                    {
                        process.OutputDataReceived += (s, ev) => { if (!string.IsNullOrEmpty(ev.Data)) _worker.ReportProgress(0, "FILE:" + ev.Data); };
                        process.ErrorDataReceived += (s, ev) => { if (!string.IsNullOrEmpty(ev.Data)) _worker.ReportProgress(0, "ERR:" + ev.Data); };
                        process.BeginOutputReadLine();
                        process.BeginErrorReadLine();
                        process.WaitForExit();

                        if (process.ExitCode != 0)
                            throw new InvalidOperationException("extract-xiso exited with code " + process.ExitCode);
                    }
                }
                else
                {
                    _worker.ReportProgress(45, "Game data already present, skipping extraction.");
                }

                _worker.ReportProgress(50, "Copying game files...");
                string distDir = GetPayloadFile("dist");
                if (!Directory.Exists(distDir))
                    throw new DirectoryNotFoundException("The 'dist' folder was not found in the installer payload.");

                var filesToCopy = Directory.GetFiles(distDir, "*", SearchOption.AllDirectories);
                int index = 0;
                foreach (var file in filesToCopy)
                {
                    string relative = file.Substring(distDir.Length + 1);
                    string target = Path.Combine(_destination, relative);
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    File.Copy(file, target, true);
                    index++;
                    int percent = 50 + (int)(35.0 * index / Math.Max(1, filesToCopy.Length));
                    _worker.ReportProgress(percent, $"Copied {relative}");
                }

                // Preserve existing settings, only update what's needed.
                _worker.ReportProgress(88, "Updating configuration...");
                string configPath = Path.Combine(_destination, "dantes_inferno.toml");
                var config = GameConfig.Load(configPath);
                // Always set the game data root and ROV path.
                config.GameDataRoot = gameDir;
                config.RenderTargetPath = "rov";
                // Force logging off by default on install/update.
                config.LogLevel = "off";
                // Set sensible defaults only if not already configured.
                if (string.IsNullOrEmpty(config.Resolution))
                    config.Resolution = "1080p";
                if (config.ResolutionScale < 1)
                    config.ResolutionScale = 1;
                if (string.IsNullOrEmpty(config.SwapPostEffect))
                    config.SwapPostEffect = "none";
                if (config.AnisotropicOverride < -1)
                    config.AnisotropicOverride = -1;
                config.VSync = true;
                config.Fullscreen = true;
                if (string.IsNullOrEmpty(config.InputBackend))
                    config.InputBackend = "sdl";
                config.Save();

                // Write the version from the payload's version.txt.
                string versionFile = GetPayloadFile("version.txt");
                string versionStr = "0.3.1-alpha";
                if (File.Exists(versionFile))
                    versionStr = File.ReadAllText(versionFile).Trim();
                string destVersionFile = Path.Combine(_destination, "version.txt");
                File.WriteAllText(destVersionFile, versionStr + "\n");
                GitHubUpdater.SetLocalVersion(_destination, SemanticVersion.Parse(versionStr));

                RegisterInAddRemovePrograms(_destination, versionStr);

                _worker.ReportProgress(100, "Installation complete.");
            }
            catch (Exception ex)
            {
                _worker.ReportProgress(0, "ERROR: " + ex.Message);
                e.Result = ex;
            }
        }

        private void Worker_ProgressChanged(object sender, ProgressChangedEventArgs e)
        {
            if (e.ProgressPercentage > 0)
            {
                InstallProgress.IsIndeterminate = false;
                InstallProgress.Value = e.ProgressPercentage;
            }

            string message = e.UserState as string;
            if (string.IsNullOrEmpty(message))
                return;

            if (message.StartsWith("FILE:"))
            {
                CurrentOperationText.Text = message.Substring(5);
                return;
            }

            if (message.StartsWith("ERR:"))
            {
                LogTextBox.AppendText(message.Substring(4) + "\n");
                LogTextBox.ScrollToEnd();
                return;
            }

            LogTextBox.AppendText(message + "\n");
            LogTextBox.ScrollToEnd();
        }

        private void Worker_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            InstallProgress.IsIndeterminate = false;

            if (e.Result is Exception ex)
            {
                MessageBox.Show("Installation failed:\n" + ex.Message, "Install Error", MessageBoxButton.OK, MessageBoxImage.Error);
                _step = 3;
                UpdateNavigation();
                return;
            }

            InstallProgress.Value = 100;
            _step = 5;
            FinishSummary.Text = $"Installed to:\n{_destination}\n\nGame data extracted to:\n{Path.Combine(_destination, "game")}\n\nClick Finish to close the installer.";
            UpdateNavigation();
        }

        private void CreateDesktopShortcut()
        {
            try
            {
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string shortcutPath = Path.Combine(desktop, "Dante's Inferno.lnk");
                string target = Path.Combine(_destination, "DantesInfernoLauncher.exe");
                string icon = Path.Combine(_destination, "DantesInfernoLauncher.exe");

                if (File.Exists(shortcutPath))
                    File.Delete(shortcutPath);

                dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
                dynamic shortcut = shell.CreateShortcut(shortcutPath);
                shortcut.TargetPath = target;
                shortcut.WorkingDirectory = _destination;
                shortcut.IconLocation = $"{icon},0";
                shortcut.Save();
            }
            catch (Exception ex)
            {
                MessageBox.Show("Could not create desktop shortcut:\n" + ex.Message, "Shortcut Error", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }

        private void RegisterInAddRemovePrograms(string installDir, string version)
        {
            try
            {
                using (var key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Uninstall\DantesInferno"))
                {
                    if (key == null) return;
                    key.SetValue("DisplayName", "Dante's Inferno");
                    key.SetValue("DisplayVersion", version);
                    key.SetValue("InstallLocation", installDir);
                    key.SetValue("DisplayIcon", Path.Combine(installDir, "DantesInfernoLauncher.exe") + ",0");
                    key.SetValue("UninstallString", Path.Combine(installDir, "uninstall.exe"));
                    key.SetValue("NoModify", 1, Microsoft.Win32.RegistryValueKind.DWord);
                    key.SetValue("NoRepair", 1, Microsoft.Win32.RegistryValueKind.DWord);
                    key.SetValue("Publisher", "florinp93");
                    key.SetValue("URLInfoAbout", "https://github.com/florinp93/dantes-inferno");
                }
            }
            catch { }
        }
    }
}
