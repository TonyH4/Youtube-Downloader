using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using yt_downloader.Properties;

namespace yt_downloader
{
	public partial class MainWindow : Form
	{
		public MainWindow()
		{
			InitializeComponent();

			this.WindowState = FormWindowState.Normal;
			this.StartPosition = FormStartPosition.Manual;
			this.Location = Settings.Default.WindowPosition;
			this.Size = Settings.Default.WindowSize;

			pathTextBox.Text = folderBrowserDialog1.SelectedPath = Settings.Default.Path;
		}

		/// <summary>
		/// Run the given command
		/// </summary>
		/// <param name="fileName">Name of the executable file</param>
		/// <param name="args">Arguments</param>
		/// <param name="waitForExit">Whether to wait for the program to exit</param>
		/// <returns>The program's return code, or 0 if <paramref name="waitForExit"></paramref> is false.</returns>
		static int system(string fileName, string args, bool waitForExit = true, bool shellExecute = false)
		{
			ProcessStartInfo startInfo = new ProcessStartInfo
			{
				FileName = fileName,
				Arguments = args,
				CreateNoWindow = true,
				UseShellExecute = shellExecute,
			};
			using (Process processHandle = Process.Start(startInfo))
			{
				if (waitForExit)
				{
					processHandle.WaitForExit();
					return processHandle.ExitCode;
				}
				else return 0;
			}
		}

		private void browseButton_Click(object sender, EventArgs e)
		{
			if (folderBrowserDialog1.ShowDialog() == DialogResult.OK) {
				pathTextBox.Text = folderBrowserDialog1.SelectedPath;
			}
		}

		private static string scriptFilename = @"yt-downloader.pyw";

		private async void downloadButton_Click(object sender, EventArgs e)
		{
			Task<int> result = new Task<int>(() => {
				string path = pathTextBox.Text;
				if (path[path.Length - 1] != Path.DirectorySeparatorChar
					&& path[path.Length - 1] != Path.AltDirectorySeparatorChar)
					path = path + Path.DirectorySeparatorChar;
				string args = string.Format("{0} {1}*.mp3", urlTextBox.Text, pathTextBox.Text);
				return system(scriptFilename, args, shellExecute:true, waitForExit:true);
			});

			Settings.Default.Path = pathTextBox.Text;
			Settings.Default.Save();

			toolStripStatusLabel1.Text = "Downloading...";
			result.Start();

			try
			{
				if (await result != 0)
					toolStripStatusLabel1.Text = "An error occured.";
				else toolStripStatusLabel1.Text = "The operation completed succesfully.";
			}
			catch (Win32Exception ex)
			{
				if (ex.NativeErrorCode == 0x02) //File not found  
					toolStripStatusLabel1.Text = scriptFilename + ": File not found";
				else toolStripStatusLabel1.Text = "Failed to run download script.";
			}
			catch (FileNotFoundException)
			{
				toolStripStatusLabel1.Text = scriptFilename + ": File not found";
			}

		}

		private void urlTextBox_Hover(object sender, EventArgs e)
		{
			if (Clipboard.ContainsText())
			{
				string clipboardText = Clipboard.GetText(TextDataFormat.UnicodeText);
				clipboardText = clipboardText.Replace("http://", "https://");
				if (clipboardText.StartsWith("https://www.youtube.com/watch?v")
					|| clipboardText.StartsWith("https://youtu.be/"))
					urlTextBox.Text = clipboardText;
			}
		}

		private void mainWindow_Resize(object sender, EventArgs e)
		{
			try
			{
				Form form = sender as Form;
				Settings.Default.WindowSize = form.Size;
				Settings.Default.Save();
			}
			catch (Exception) { }
		}

		private void mainWindow_Move(object sender, EventArgs e)
		{
			try
			{
				Form form = sender as Form;
				Settings.Default.WindowPosition = form.Location;
				Settings.Default.Save();
			}
			catch (Exception) { }
		}
	}
}
