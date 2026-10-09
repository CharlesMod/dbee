#!/bin/sh
# Healthy: the cron entry that floods is gone, the log filesystem under 90%, patient-web answering.
dir=/var/log/patient
used=$(df -P "$dir" | awk 'NR==2{u=$5; sub("%","",u); print u}')
if grep -qsE '^[[:space:]]*[^#[:space:]].*report\.log' /etc/cron.d/* 2>/dev/null; then cron=present; else cron=gone; fi
active=$(systemctl is-active patient-web.service)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
echo "$dir ${used}% used; flooding cron entry $cron; patient-web $active; http $code"
[ "$used" -lt 90 ] && [ "$cron" = gone ] && [ "$active" = active ] && [ "$code" = 200 ]
