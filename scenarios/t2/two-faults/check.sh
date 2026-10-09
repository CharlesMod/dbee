#!/bin/sh
# Healthy: patient-web itself (not a squatter) holds :8080 and answers, and the user it
# runs as can write its log.
dir=/var/log/patient
u=$(systemctl show -p User --value patient-web.service); u=${u:-root}
if runuser -u "$u" -- test -w "$dir" 2>/dev/null; then w=writable; else w=NOT-writable; fi
pid=$(ss -ltnpH 'sport = :8080' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1)
cg=$(cat /proc/$pid/cgroup 2>/dev/null | tail -1)
active=$(systemctl is-active patient-web.service)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
echo "8080 held by pid ${pid:-none} ($cg); $dir $w by $u; patient-web $active; http $code"
[ -n "$pid" ] && echo "$cg" | grep -q patient-web.service && [ "$w" = writable ] && [ "$active" = active ] && [ "$code" = 200 ]
