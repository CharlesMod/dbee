# a preview server (its own PowerShell process) took 127.0.0.1:18080 while patient-web was
# down, so patient-web cannot bind (only one usage of each socket address) and restarts into it.
Assert-Clean
Install-Patient
Stop-Service $Svc -Force
for ($i = 0; $i -lt 10 -and (Get-Listener); $i++) { Start-Sleep -Milliseconds 500 }
@'
$l = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 18080); $l.Start()
while ($true) { $c = $l.AcceptTcpClient(); $c.Close() }
'@ | Set-Content -Encoding ascii "$D\preview.ps1"
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$D\preview.ps1"
for ($i = 0; $i -lt 20 -and -not (Get-Listener); $i++) { Start-Sleep -Milliseconds 500 }
Start-Broken
$l = Get-Listener
"seeded: $Port held by pid $($l.OwningProcess) ($D\preview.ps1); $Svc $((Get-Service $Svc).Status)"
