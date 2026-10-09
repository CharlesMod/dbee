#!/bin/sh
# Return the patient: the squatter goes, patient-web is reset and started.
m=/opt/dbee/.seeded-port-taken
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop preview-http.service 2>/dev/null
systemctl reset-failed preview-http.service patient-web.service 2>/dev/null
rm -f "$m"
systemctl restart patient-web.service
sleep 2
echo "unseeded: patient-web $(systemctl is-active patient-web.service)"
