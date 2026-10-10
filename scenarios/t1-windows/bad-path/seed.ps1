# a cleanup moved the service's program into bin.old, so the Service Control Manager
# cannot find the file it was told to start.
Assert-Clean
Install-Patient
Stop-Service $Svc -Force
Start-Sleep -Seconds 1
Move-Item "$D\bin" "$D\bin.old"
Start-Broken
"seeded: $Exe moved to $D\bin.old; $Svc $((Get-Service $Svc).Status)"
