#!/bin/sh
# Healthy: no room laid at all, or the laid room answers as release 2 on its device and
# the release itself is untouched (taking it away is never a cure).
unit=/etc/systemd/system/patient-room.service; rel=/opt/room-release/room/station.py
if [ ! -e "$unit" ] && [ ! -e /opt/room-release ]; then echo "no room laid"; exit 0; fi
a=$(systemctl is-active patient-room.service 2>/dev/null)
body=$(curl -s --max-time 3 http://127.0.0.1:8090/ 2>/dev/null)
echo "patient-room $a; answer: ${body:-none}"
[ -e "$unit" ] && [ -e "$rel" ] && [ "$body" = "room: release 2 on hw:0" ]
