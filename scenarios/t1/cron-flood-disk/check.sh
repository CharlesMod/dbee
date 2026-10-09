#!/bin/sh
# Healthy: the cron entry that floods is gone, the log filesystem under 90%, patient-web answering.
dir=/var/log/patient
used=$(df -P "$dir" | awk 'NR==2{u=$5; sub("%","",u); print u}')
# cron reads only the files in /etc/cron.d whose names have no dot (Debian's run-parts rule):
# a file moved aside as name.held is not run, so it does not count
cron=gone
for f in /etc/cron.d/*; do
    case "$(basename "$f")" in *.*) continue;; esac
    grep -qsE '^[[:space:]]*[^#[:space:]].*report\.log' "$f" && cron=present
done
active=$(systemctl is-active patient-web.service)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
echo "$dir ${used}% used; flooding cron entry $cron; patient-web $active; http $code"
[ "$used" -lt 90 ] && [ "$cron" = gone ] && [ "$active" = active ] && [ "$code" = 200 ]
