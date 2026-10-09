#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the squatter goes, patient-web is reset and started.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop preview-http.service 2>/dev/null
systemctl reset-failed preview-http.service patient-web.service 2>/dev/null
rm -f "$m"
systemctl restart patient-web.service
sleep 2
echo "unseeded: patient-web $(systemctl is-active patient-web.service)"
