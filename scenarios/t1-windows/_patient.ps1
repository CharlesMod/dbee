# The Windows patient every t1-windows scenario shares: patient-web, a small site served
# by a real Windows service (DBeePatientWeb, a .NET ServiceBase compiled here, running as
# LocalService) on 127.0.0.1:18080, its files in C:\ProgramData\DBeePatient. Put before
# each step by the sim; the steps touch only this service, its folder and its event source.
$ErrorActionPreference = 'Continue'
$Svc = 'DBeePatientWeb'; $D = 'C:\ProgramData\DBeePatient'; $Exe = "$D\bin\patientweb.exe"
$Port = 18080; $Acct = 'NT AUTHORITY\LocalService'
$Seeded = "$D\.seeded"

$PatientSrc = @'
using System; using System.IO; using System.Net; using System.Net.Sockets; using System.Text;
using System.Threading; using System.ServiceProcess;
public class PatientWeb : ServiceBase {
    const string Home = @"C:\ProgramData\DBeePatient";
    TcpListener listener; string page;
    public PatientWeb() { ServiceName = "DBeePatientWeb"; AutoLog = true; }
    protected override void OnStart(string[] args) {
        string conf = Path.Combine(Home, "patient.conf");
        int port = 0;
        foreach (string line in File.ReadAllLines(conf))
            if (line.Trim().StartsWith("port=")) int.TryParse(line.Trim().Substring(5), out port);
        if (port == 0) throw new InvalidDataException("patient-web: cannot read a port from " + conf);
        page = Path.Combine(Home, "site", "index.html");
        listener = new TcpListener(IPAddress.Loopback, port);
        listener.Start();
        new Thread(Serve) { IsBackground = true }.Start();
    }
    void Serve() {
        while (listener != null) {
            try {
                using (TcpClient c = listener.AcceptTcpClient()) {
                    NetworkStream s = c.GetStream(); s.Read(new byte[4096], 0, 4096);
                    byte[] body = File.ReadAllBytes(page);
                    byte[] head = Encoding.ASCII.GetBytes("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nContent-Length: " +
                                                          body.Length + "\r\nConnection: close\r\n\r\n");
                    s.Write(head, 0, head.Length); s.Write(body, 0, body.Length);
                }
            } catch (Exception) { }
        }
    }
    protected override void OnStop() { TcpListener l = listener; listener = null; if (l != null) l.Stop(); }
    public static void Main() { ServiceBase.Run(new PatientWeb()); }
}
'@

function Test-Admin { ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
function Get-Listener { Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 }
function Get-Http { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$Port/").StatusCode } catch { 0 } }
function Wait-Http($want) { for ($i = 0; $i -lt 20; $i++) { if ((Get-Http) -eq $want) { return $true }; Start-Sleep -Milliseconds 500 }; $false }

# Refused (exit 4) unless this is an admin shell with nothing of ours here and the port free.
function Assert-Clean {
    if (-not (Test-Admin)) { 'refused: not an admin shell'; exit 4 }
    if (Test-Path $Seeded) { 'refused: already seeded'; exit 4 }
    if (Get-Service -Name $Svc -ErrorAction SilentlyContinue) { "refused: $Svc exists already"; exit 4 }
    if (Get-Listener) { "refused: $Port is taken before the seed"; exit 4 }
}

# The patient, healthy: built, installed, serving. Exit 4 if it never comes up.
function Install-Patient {
    New-Item -ItemType Directory -Force "$D\bin", "$D\site" | Out-Null
    New-Item -ItemType File -Force $Seeded | Out-Null
    '<h1>patient</h1>' | Set-Content -Encoding ascii "$D\site\index.html"
    "port=$Port" | Set-Content -Encoding ascii "$D\patient.conf"
    Add-Type -TypeDefinition $PatientSrc -ReferencedAssemblies System.ServiceProcess -OutputAssembly $Exe -OutputType ConsoleApplication
    icacls $D /grant "${Acct}:(OI)(CI)RX" | Out-Null
    if (-not [Diagnostics.EventLog]::SourceExists($Svc)) { New-EventLog -LogName Application -Source $Svc }
    sc.exe create $Svc binPath= "`"$Exe`"" obj= $Acct start= auto DisplayName= 'Patient Web' | Out-Null
    sc.exe failure $Svc reset= 60 actions= restart/5000/restart/5000/restart/5000 | Out-Null
    sc.exe failureflag $Svc 1 | Out-Null
    Start-Service $Svc
    if (-not (Wait-Http 200)) { 'refused: the patient did not come up'; exit 4 }
}

function Start-Broken { try { Start-Service $Svc -ErrorAction Stop } catch { } ; Start-Sleep -Seconds 3 }

# Healthy: no patient here, or its own service (not a squatter) holds the port and answers.
function Test-Healthy {
    $s = Get-CimInstance Win32_Service -Filter "Name='$Svc'"
    if (-not $s) { 'no patient web here'; exit 0 }
    $l = Get-Listener; $code = Get-Http
    "$Svc $($s.State) pid $($s.ProcessId); $Port held by $(if ($l) { $l.OwningProcess } else { 'nobody' }); http $code"
    if ($s.State -eq 'Running' -and $l -and $l.OwningProcess -eq $s.ProcessId -and $code -eq 200) { exit 0 }
    exit 1
}

# Return the machine: the service, the squatter, the event source and the folder go.
function Remove-Patient {
    if (-not (Test-Path $Seeded)) { 'nothing seeded here'; exit 0 }
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object CommandLine -like '*DBeePatient\preview.ps1*' |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Service $Svc -Force -ErrorAction SilentlyContinue
    sc.exe delete $Svc | Out-Null
    if ([Diagnostics.EventLog]::SourceExists($Svc)) { Remove-EventLog -Source $Svc }
    icacls $D /reset /T /C /Q | Out-Null
    Remove-Item -Recurse -Force $D -ErrorAction SilentlyContinue
    'unseeded'; exit 0
}
