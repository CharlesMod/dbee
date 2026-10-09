#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the guarded unit and the lock go, plain patient-web runs again.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop patient-web-locked.service 2>/dev/null
rm -f /run/patient/web.lock /etc/systemd/system/patient-web-locked.service
rmdir /run/patient 2>/dev/null
systemctl daemon-reload
systemctl reset-failed patient-web-locked.service patient-web.service 2>/dev/null
rm -f "$m"
systemctl restart patient-web.service
sleep 2
echo "unseeded: patient-web $(systemctl is-active patient-web.service)"
