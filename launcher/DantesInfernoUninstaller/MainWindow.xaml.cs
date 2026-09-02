using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows;

namespace DantesInferno.Uninstaller
{
    public partial class MainWindow : Window
    {
        private string _installDir;

        public MainWindow()
        {
            InitializeComponent();
            _installDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        }

        private void CancelButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        private void UninstallButton_Click(object sender, RoutedEventArgs e)
        {
            UninstallButton.IsEnabled = false;
            CancelButton.IsEnabled = false;

            bool keepSaves = KeepSavesCheck.IsChecked ?? true;

            try
            {
                DeleteDesktopShortcut();
                RemoveAddRemoveProgramsEntry();

                if (keepSaves)
                {
                    PreserveDataAndDelete();
                }
                else
                {
                    DeleteEverything();
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Uninstall encountered an error:\n" + ex.Message, "Uninstall Error", MessageBoxButton.OK, MessageBoxImage.Warning);
            }

            MessageBox.Show("Dante's Inferno has been uninstalled.", "Uninstall Complete", MessageBoxButton.OK, MessageBoxImage.Information);

            SelfDeleteAndClose();
        }

        private void DeleteDesktopShortcut()
        {
            try
            {
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string shortcutPath = Path.Combine(desktop, "Dante's Inferno.lnk");
                if (File.Exists(shortcutPath))
                    File.Delete(shortcutPath);
            }
            catch { }
        }

        private void RemoveAddRemoveProgramsEntry()
        {
            try
            {
                using (var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Uninstall\DantesInferno", true))
                {
                    if (key != null)
                        key.DeleteSubKeyTree("");
                }
            }
            catch { }
        }

        private void PreserveDataAndDelete()
        {
            string tempDir = Path.Combine(Path.GetTempPath(), "DantesInferno_Backup_" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(tempDir);

            PreserveFolder("saves", tempDir);
            PreserveFolder("logs", tempDir);

            try
            {
                Directory.Delete(_installDir, true);
            }
            catch
            {
                TryDeleteFiles();
            }

            string restoreDir = _installDir;
            Directory.CreateDirectory(restoreDir);

            RestoreFolder("saves", tempDir, restoreDir);
            RestoreFolder("logs", tempDir, restoreDir);

            try { Directory.Delete(tempDir, true); } catch { }
        }

        private void DeleteEverything()
        {
            try
            {
                Directory.Delete(_installDir, true);
            }
            catch
            {
                TryDeleteFiles();
            }
        }

        private void PreserveFolder(string folderName, string tempDir)
        {
            string src = Path.Combine(_installDir, folderName);
            if (Directory.Exists(src))
            {
                string dst = Path.Combine(tempDir, folderName);
                CopyDirectory(src, dst);
            }
        }

        private void RestoreFolder(string folderName, string tempDir, string restoreDir)
        {
            string src = Path.Combine(tempDir, folderName);
            if (Directory.Exists(src))
            {
                string dst = Path.Combine(restoreDir, folderName);
                CopyDirectory(src, dst);
            }
        }

        private void CopyDirectory(string src, string dst)
        {
            Directory.CreateDirectory(dst);
            foreach (var file in Directory.GetFiles(src, "*", SearchOption.AllDirectories))
            {
                string relative = file.Substring(src.Length + 1);
                string target = Path.Combine(dst, relative);
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                File.Copy(file, target, true);
            }
        }

        private void TryDeleteFiles()
        {
            try
            {
                foreach (var file in Directory.GetFiles(_installDir, "*", SearchOption.AllDirectories))
                {
                    try { File.Delete(file); } catch { }
                }
                foreach (var dir in Directory.GetDirectories(_installDir, "*", SearchOption.AllDirectories))
                {
                    try { if (Directory.Exists(dir)) Directory.Delete(dir, true); } catch { }
                }
                foreach (var file in Directory.GetFiles(_installDir))
                {
                    try { File.Delete(file); } catch { }
                }
            }
            catch { }
        }

        private void SelfDeleteAndClose()
        {
            string exePath = Assembly.GetExecutingAssembly().Location;
            string batchPath = Path.Combine(Path.GetTempPath(), "dantes_uninstall_cleanup.bat");

            string batch = string.Format(
                "@echo off\r\n" +
                "timeout /t 2 /nobreak >nul\r\n" +
                "del \"{0}\"\r\n" +
                "del \"{1}\"\r\n",
                exePath, batchPath);

            File.WriteAllText(batchPath, batch);

            Process.Start(new ProcessStartInfo
            {
                FileName = batchPath,
                WindowStyle = ProcessWindowStyle.Hidden,
                CreateNoWindow = true,
                UseShellExecute = false,
            });

            Close();
        }
    }
}
