#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the squatter and the drop-in go, patient-web runs as root again.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop preview-http.service 2>/dev/null
rm -rf /etc/systemd/system/patient-web.service.d
chown root:root /var/log/patient; chmod 0755 /var/log/patient
systemctl daemon-reload
systemctl reset-failed preview-http.service patient-web.service 2>/dev/null
rm -f "$m"
systemctl restart patient-web.service
sleep 2
echo "unseeded: patient-web $(systemctl is-active patient-web.service)"
