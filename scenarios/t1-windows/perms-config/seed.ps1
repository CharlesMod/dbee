# patient.conf was replaced by a copy that denies the service's account reading it, so
# OnStart throws Access denied and the Service Control Manager restarts it into the same failure.
Assert-Clean
Install-Patient
Stop-Service $Svc -Force
icacls "$D\patient.conf" /deny "${Acct}:(R)" | Out-Null
Start-Broken
"seeded: $Acct denied reading $D\patient.conf; $Svc $((Get-Service $Svc).Status)"
