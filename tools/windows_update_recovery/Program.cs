using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows.Forms;

namespace MailDeskUpdateRecovery
{
    internal static class Program
    {
        private const string Title = "MailDesk v0.3.9 文件夹版升级修复";

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string executable = ResolveExecutable(args);
            if (string.IsNullOrEmpty(executable))
            {
                return 1;
            }

            string applicationDirectory = Path.GetDirectoryName(executable);
            if (
                string.IsNullOrEmpty(applicationDirectory) ||
                !Directory.Exists(Path.Combine(applicationDirectory, "_internal"))
            )
            {
                ShowError("选择的文件不是 MailDesk 文件夹版中的 MailDesk.exe。");
                return 2;
            }

            if (Process.GetProcessesByName("MailDesk").Any(process => !process.HasExited))
            {
                ShowError("请先从系统托盘彻底退出正在运行的 MailDesk，然后重新运行本工具。");
                return 3;
            }

            DirectoryInfo parent = Directory.GetParent(applicationDirectory);
            string safeWorkingDirectory = parent == null
                ? applicationDirectory
                : parent.FullName;

            try
            {
                Process.Start(
                    new ProcessStartInfo
                    {
                        FileName = executable,
                        WorkingDirectory = safeWorkingDirectory,
                        UseShellExecute = true,
                    }
                );
            }
            catch (Exception exception)
            {
                ShowError("无法启动 MailDesk：" + exception.Message);
                return 4;
            }

            MessageBox.Show(
                "MailDesk 已从安全目录启动。\n\n"
                    + "现在请在软件中重新检查更新，并点击“重启并安装”。"
                    + "升级过程会保留旁边的 MailDesk Data 用户数据。",
                Title,
                MessageBoxButtons.OK,
                MessageBoxIcon.Information
            );
            return 0;
        }

        private static string ResolveExecutable(string[] args)
        {
            if (args.Length > 0)
            {
                string supplied = Path.GetFullPath(args[0].Trim('"'));
                if (File.Exists(supplied))
                {
                    return supplied;
                }
            }

            using (OpenFileDialog dialog = new OpenFileDialog())
            {
                dialog.Title = "选择 v0.3.9 文件夹版中的 MailDesk.exe";
                dialog.Filter = "MailDesk.exe|MailDesk.exe";
                dialog.CheckFileExists = true;
                dialog.Multiselect = false;
                return dialog.ShowDialog() == DialogResult.OK
                    ? Path.GetFullPath(dialog.FileName)
                    : string.Empty;
            }
        }

        private static void ShowError(string message)
        {
            MessageBox.Show(
                message,
                Title,
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
}
