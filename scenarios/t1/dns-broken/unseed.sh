#!/bin/sh
mkdir -p /run/.sim
# Return the patient: resolv.conf from the held copy, the fetch unit gone.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
[ -e /etc/resolv.conf.held ] && { cat /etc/resolv.conf.held > /etc/resolv.conf; rm -f /etc/resolv.conf.held; }
systemctl stop patient-fetch.service 2>/dev/null
rm -f /etc/systemd/system/patient-fetch.service
systemctl daemon-reload
systemctl reset-failed patient-fetch.service 2>/dev/null
rm -f "$m"
echo "unseeded: resolv.conf -> $(grep nameserver /etc/resolv.conf | head -1)"
