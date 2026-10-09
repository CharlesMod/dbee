#!/bin/sh
# Healthy: the page answers, and no lock file names a dead pid.
lock=/run/patient/web.lock
if [ -e "$lock" ]; then
    p=$(cat "$lock" 2>/dev/null)
    if kill -0 "$p" 2>/dev/null; then l="lock held by live pid $p"; stale=0; else l="lock holds dead pid $p"; stale=1; fi
else l="no lock file"; stale=0; fi
a=$(systemctl is-active patient-web.service); b=$(systemctl is-active patient-web-locked.service 2>/dev/null)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
echo "$l; patient-web $a; patient-web-locked $b; http $code"
[ "$stale" = 0 ] && [ "$code" = 200 ]
