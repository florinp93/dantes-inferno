using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace DantesInferno.Installer
{
    public partial class MainWindow : Window
    {
        private int _step = 1;
        private string _destination;
        private string _isoPath;
        private string _installerDir;
        private readonly BackgroundWorker _worker = new BackgroundWorker();

        public MainWindow()
        {
            InitializeComponent();
            InitializeTheme();
            _installerDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
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

        private void UpdateNavigation()
        {
            Step1Welcome.Visibility = _step == 1 ? Visibility.Visible : Visibility.Collapsed;
            Step2Destination.Visibility = _step == 2 ? Visibility.Visible : Visibility.Collapsed;
            Step3Iso.Visibility = _step == 3 ? Visibility.Visible : Visibility.Collapsed;
            Step4Progress.Visibility = _step == 4 ? Visibility.Visible : Visibility.Collapsed;
            Step5Finish.Visibility = _step == 5 ? Visibility.Visible : Visibility.Collapsed;

            BackButton.IsEnabled = _step > 1 && _step < 5;
            NextButton.IsEnabled = _step < 5;
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
                if (Directory.Exists(gameDir))
                {
                    _worker.ReportProgress(5, "Removing old game data...");
                    Directory.Delete(gameDir, true);
                }

                _worker.ReportProgress(10, "Extracting ISO to game folder...");
                string extractExe = Path.Combine(_installerDir, "extract-xiso.exe");
                if (!File.Exists(extractExe))
                    throw new FileNotFoundException("extract-xiso.exe was not found next to the installer.");

                var psi = new ProcessStartInfo
                {
                    FileName = extractExe,
                    Arguments = $"\"{_isoPath}\" -d \"{gameDir}\" -s -q",
                    WorkingDirectory = _destination,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };

                using (var process = Process.Start(psi))
                {
                    process.WaitForExit();
                    string errors = process.StandardError.ReadToEnd();
                    if (process.ExitCode != 0 && !string.IsNullOrWhiteSpace(errors))
                        throw new InvalidOperationException("extract-xiso failed: " + errors);
                }

                _worker.ReportProgress(50, "Copying ReXGlue game files...");
                string distDir = Path.Combine(_installerDir, "dist");
                if (!Directory.Exists(distDir))
                    throw new DirectoryNotFoundException("The 'dist' folder was not found next to the installer. Build a release first.");

                var filesToCopy = Directory.GetFiles(distDir, "*", SearchOption.AllDirectories);
                int index = 0;
                foreach (var file in filesToCopy)
                {
                    string relative = file.Substring(distDir.Length + 1);
                    string target = Path.Combine(_destination, relative);
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    File.Copy(file, target, true);
                    index++;
                    int percent = 50 + (int)(40.0 * index / Math.Max(1, filesToCopy.Length));
                    _worker.ReportProgress(percent, $"Copied {relative}");
                }

                _worker.ReportProgress(90, "Writing default configuration...");
                string configPath = Path.Combine(_destination, "dantes_inferno.toml");
                var config = GameConfig.Load(configPath);
                config.GameDataRoot = gameDir;
                config.Resolution = "1080p";
                config.RenderTargetPath = "rov";
                config.Save();

                GitHubUpdater.SetLocalVersion(_destination, SemanticVersion.Parse("0.1.0-alpha"));

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
            InstallProgress.Value = e.ProgressPercentage;
            LogTextBox.AppendText((e.UserState as string) + "\n");
            LogTextBox.ScrollToEnd();
        }

        private void Worker_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            if (e.Result is Exception ex)
            {
                MessageBox.Show("Installation failed:\n" + ex.Message, "Install Error", MessageBoxButton.OK, MessageBoxImage.Error);
                _step = 3;
                UpdateNavigation();
                return;
            }

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
    }
}
