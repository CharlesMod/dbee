#!/bin/sh
# Healthy: patient-web itself (not a squatter) holds :8080 and answers.
pid=$(ss -ltnpH 'sport = :8080' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1)
cg=$(cat /proc/$pid/cgroup 2>/dev/null | tail -1)
active=$(systemctl is-active patient-web.service)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
echo "8080 held by pid ${pid:-none} ($cg); patient-web $active; http $code"
[ -n "$pid" ] && echo "$cg" | grep -q patient-web.service && [ "$active" = active ] && [ "$code" = 200 ]
