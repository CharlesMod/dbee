#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the room's unit, its drop-ins, the release and the old checkout go.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop patient-room.service 2>/dev/null
rm -f /etc/systemd/system/patient-room.service /etc/systemd/system/patient-room.service.d/*.conf
rmdir /etc/systemd/system/patient-room.service.d 2>/dev/null
for d in /opt/room-release/room /home/bee/room /home/bee/room.*; do
    [ -d "$d" ] || continue
    rm -f "$d"/*.py "$d"/__pycache__/*; rmdir "$d"/__pycache__ "$d" 2>/dev/null
done
rmdir /opt/room-release /home/bee 2>/dev/null
systemctl daemon-reload
systemctl reset-failed patient-room.service 2>/dev/null
rm -f "$m"
echo "unseeded: patient-room gone"
