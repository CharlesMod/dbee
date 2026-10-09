#!/bin/sh
# Healthy: the user patient-web runs as can write its log, and the service answers.
dir=/var/log/patient
u=$(systemctl show -p User --value patient-web.service); u=${u:-root}
if runuser -u "$u" -- test -w "$dir" 2>/dev/null; then w=writable; else w=NOT-writable; fi
active=$(systemctl is-active patient-web.service)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
echo "$dir $(stat -c '%U:%G %a' "$dir") $w by $u; patient-web $active; http $code"
[ "$w" = writable ] && [ "$active" = active ] && [ "$code" = 200 ]
