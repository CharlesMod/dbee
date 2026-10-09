#!/bin/sh
# Healthy: the log's filesystem under 90% and patient-web answering. Prints what it read.
dir=/var/log/patient
used=$(df -P "$dir" | awk 'NR==2{u=$5; sub("%","",u); print u}')
active=$(systemctl is-active patient-web.service)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
echo "$dir ${used}% used; patient-web $active; http $code"
[ "$used" -lt 90 ] && [ "$active" = active ] && [ "$code" = 200 ]
