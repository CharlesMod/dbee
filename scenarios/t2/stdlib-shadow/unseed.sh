#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the room's unit, its drop-ins and its app go.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop patient-room.service 2>/dev/null
rm -f /etc/systemd/system/patient-room.service /etc/systemd/system/patient-room.service.d/*.conf
rmdir /etc/systemd/system/patient-room.service.d 2>/dev/null
rm -f /opt/room/app/*.py /opt/room/app/*.py.* /opt/room/app/__pycache__/*
rmdir /opt/room/app/__pycache__ /opt/room/app /opt/room 2>/dev/null
systemctl daemon-reload
systemctl reset-failed patient-room.service 2>/dev/null
rm -f "$m"
echo "unseeded: patient-room gone"
