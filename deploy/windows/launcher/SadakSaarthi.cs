// SADAKSAARTHI launcher.
// Starts the local backend (it also serves the ICCC dashboard and the /field phone page), waits until it answers,
// opens the browser, and stops the backend again when this window closes.
//
// Build:  deploy\windows\build-exe.bat   (uses the C# 5 compiler that ships with Windows, so no SDK is needed)
// Keep SadakSaarthi.exe inside the project folder: it looks for backend\app\main.py from its own folder upwards.
// Set SADAKSAARTHI_NO_BROWSER=1 to start without opening the browser.

using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Threading;

static class Launcher
{
    const int Port = 8000;
    static readonly string Url = "http://127.0.0.1:" + Port + "/";

    // A Windows job object makes everything this exe starts die with it, even if the console window is closed.
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll")]
    static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint size);
    [DllImport("kernel32.dll")]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [StructLayout(LayoutKind.Sequential)]
    struct BasicLimits
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters
    {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct ExtendedLimits
    {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }

    static IntPtr KillOnCloseJob()
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        ExtendedLimits limits = new ExtendedLimits();
        limits.Basic.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        int size = Marshal.SizeOf(typeof(ExtendedLimits));
        IntPtr mem = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(limits, mem, false);
            SetInformationJobObject(job, 9, mem, (uint)size); // 9 = JobObjectExtendedLimitInformation
        }
        finally
        {
            Marshal.FreeHGlobal(mem);
        }
        return job;
    }

    static int Main()
    {
        Console.Title = "SADAKSAARTHI";
        try
        {
            return Run();
        }
        catch (Exception ex)
        {
            return Fail("Unexpected error: " + ex.Message);
        }
    }

    static int Fail(string message)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("[x] " + message);
        Console.ResetColor();
        Console.WriteLine();
        Console.WriteLine("Press any key to close.");
        try { Console.ReadKey(true); } catch (InvalidOperationException) { }
        return 1;
    }

    static string FindRoot()
    {
        DirectoryInfo dir = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
        while (dir != null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "backend", "app", "main.py"))) return dir.FullName;
            dir = dir.Parent;
        }
        return null;
    }

    static int HealthCode()
    {
        try
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(Url + "health");
            request.Timeout = 2500;
            request.Proxy = null;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            {
                return (int)response.StatusCode;
            }
        }
        catch (WebException ex)
        {
            HttpWebResponse failed = ex.Response as HttpWebResponse;
            return failed != null ? (int)failed.StatusCode : 0;
        }
        catch (Exception)
        {
            return 0;
        }
    }

    static bool PortOpen()
    {
        try
        {
            using (TcpClient client = new TcpClient())
            {
                IAsyncResult attempt = client.BeginConnect("127.0.0.1", Port, null, null);
                if (!attempt.AsyncWaitHandle.WaitOne(800)) return false;
                client.EndConnect(attempt);
                return client.Connected;
            }
        }
        catch (Exception)
        {
            return false;
        }
    }

    static void OpenBrowser()
    {
        if (Environment.GetEnvironmentVariable("SADAKSAARTHI_NO_BROWSER") == "1") return;
        try
        {
            Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
        }
        catch (Exception)
        {
            Console.WriteLine("Open " + Url + " in your browser.");
        }
    }

    static void Stop(Process backend)
    {
        try
        {
            if (backend != null && !backend.HasExited) backend.Kill();
        }
        catch (Exception) { }
    }

    static int Run()
    {
        string root = FindRoot();
        if (root == null)
            return Fail("Cannot find the project. Keep SadakSaarthi.exe inside the project folder, next to backend\\ and dashboard\\.");

        string python = Path.Combine(root, "backend", ".venv", "Scripts", "python.exe");
        if (!File.Exists(python))
            return Fail("backend\\.venv is missing. Create it once:\r\n    cd backend\r\n    python -m venv .venv\r\n    .venv\\Scripts\\pip install -r requirements.txt");

        Console.WriteLine("SADAKSAARTHI local server");
        Console.WriteLine();

        if (HealthCode() == 200)
        {
            Console.WriteLine("The backend is already running on port " + Port + ". Opening it.");
            OpenBrowser();
            return 0;
        }
        if (PortOpen())
            return Fail("Port " + Port + " is used by another program. Close it and start again.");

        if (!File.Exists(Path.Combine(root, "backend", "static_dash", "index.html")))
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("[!] backend\\static_dash is missing, so the dashboard page will be empty.");
            Console.WriteLine("    Run scripts\\build-ui.bat once, then start again.");
            Console.ResetColor();
        }

        string logDir = Path.Combine(root, "logs");
        Directory.CreateDirectory(logDir);
        StreamWriter log = new StreamWriter(Path.Combine(logDir, "backend.log"), true);
        log.AutoFlush = true;
        log.WriteLine("---- " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " start ----");

        ProcessStartInfo info = new ProcessStartInfo(python, "-m uvicorn app.main:app --host 127.0.0.1 --port " + Port);
        info.WorkingDirectory = Path.Combine(root, "backend");
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;

        Process backend = new Process();
        backend.StartInfo = info;
        DataReceivedEventHandler write = delegate(object sender, DataReceivedEventArgs e)
        {
            if (e.Data != null) { lock (log) { log.WriteLine(e.Data); } }
        };
        backend.OutputDataReceived += write;
        backend.ErrorDataReceived += write;
        backend.Start();
        backend.BeginOutputReadLine();
        backend.BeginErrorReadLine();

        IntPtr job = KillOnCloseJob();
        AssignProcessToJobObject(job, backend.Handle);

        Console.CancelKeyPress += delegate { Stop(backend); };

        Console.Write("Starting the backend");
        bool up = false;
        for (int second = 0; second < 90; second++)
        {
            if (backend.HasExited)
            {
                Console.WriteLine();
                return Fail("The backend stopped while starting. Read logs\\backend.log for the reason.");
            }
            if (HealthCode() == 200) { up = true; break; }
            Console.Write(".");
            Thread.Sleep(1000);
        }
        Console.WriteLine();
        if (!up)
        {
            Stop(backend);
            return Fail("The backend did not answer within 90 seconds. Read logs\\backend.log for the reason.");
        }

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("Running.");
        Console.ResetColor();
        Console.WriteLine("  Dashboard : " + Url);
        Console.WriteLine("  Phone page: " + Url + "field");
        Console.WriteLine("  API docs  : " + Url + "docs");
        Console.WriteLine("  Log       : logs\\backend.log");
        Console.WriteLine();
        Console.WriteLine("Press Q or close this window to stop.");
        OpenBrowser();

        while (!backend.HasExited)
        {
            try
            {
                if (Console.KeyAvailable && Console.ReadKey(true).Key == ConsoleKey.Q) break;
            }
            catch (InvalidOperationException) { }
            Thread.Sleep(300);
        }
        Stop(backend);
        lock (log) { log.WriteLine("---- stop ----"); }
        return 0;
    }
}
