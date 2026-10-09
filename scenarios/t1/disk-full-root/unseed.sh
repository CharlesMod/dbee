#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the grown log and the filler go, the service is reset and started.
log=/var/log/patient/web.log
dir=$(dirname "$log")
[ -e "/run/.sim/seeded" ] || { echo "nothing seeded here"; exit 0; }
: > "$log"
rm -f "$dir/web.log.1" "/run/.sim/seeded"
systemctl reset-failed patient-web.service 2>/dev/null
systemctl restart patient-web.service
sleep 2
echo "unseeded: $(df -Ph "$dir" | awk 'NR==2{print $5}') used; patient-web $(systemctl is-active patient-web.service)"
