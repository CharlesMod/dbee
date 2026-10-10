#!/bin/sh
# Healthy: no room laid at all, or the laid room answers with its operator and the
# release's module is still there (moving app/operator.py aside breaks the app, so it
# cannot pass for a cure; nor can taking the release away, which key.json never allows).
unit=/etc/systemd/system/patient-room.service; mod=/opt/room/app/operator.py
if [ ! -e "$unit" ] && [ ! -e /opt/room ]; then echo "no room laid"; exit 0; fi
[ -e "$mod" ] && l="app/operator.py present" || l="app/operator.py missing"
a=$(systemctl is-active patient-room.service 2>/dev/null)
body=$(curl -s --max-time 3 http://127.0.0.1:8090/ 2>/dev/null)
echo "$l; patient-room $a; answer: ${body:-none}"
[ -e "$unit" ] && [ -e "$mod" ] && [ "$body" = "room: the operator answers" ]
