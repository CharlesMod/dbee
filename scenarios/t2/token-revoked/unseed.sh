#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the supplier stand-in, the sync unit, the token and the feed go.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop patient-upstream.service patient-sync.service 2>/dev/null
rm -rf /opt/upstream /etc/patient /var/lib/patient-feed.json /etc/systemd/system/patient-sync.service
systemctl daemon-reload
systemctl reset-failed patient-upstream.service patient-sync.service 2>/dev/null
rm -f "$m"
echo "unseeded"
