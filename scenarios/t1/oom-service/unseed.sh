#!/bin/sh
# Return the patient: the unit, its script, any drop-in the cure added and the ready file go.
m=/opt/dbee/.seeded-oom-service
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop patient-batch.service 2>/dev/null
systemctl disable patient-batch.service >/dev/null 2>&1
rm -rf /etc/systemd/system/patient-batch.service /etc/systemd/system/patient-batch.service.d /usr/local/bin/patient-batch /run/patient-batch.ready
systemctl daemon-reload
systemctl reset-failed patient-batch.service 2>/dev/null
rm -f "$m"
echo "unseeded: patient-batch $(systemctl is-active patient-batch.service 2>&1)"
