#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the probe goes, /srv/patient is the plain site again.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop patient-db-probe.service patient-web.service 2>/dev/null
rm -rf /srv/patient
[ -d /srv/releases/2026-10-07 ] && mv /srv/releases/2026-10-07 /srv/patient
mkdir -p /srv/patient; echo "<h1>patient</h1>" > /srv/patient/index.html
rm -rf /srv/releases
systemctl reset-failed patient-db-probe.service patient-web.service 2>/dev/null
rm -f "$m"
systemctl restart patient-web.service
sleep 2
echo "unseeded: patient-web $(systemctl is-active patient-web.service)"
