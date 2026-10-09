#!/bin/sh
# Healthy: no supplier sync on this machine, or the sync's token is accepted by the
# supplier. Only a new token from the supplier makes a seeded patient pass; nothing on
# this machine can.
[ -e /etc/systemd/system/patient-sync.service ] || { echo "no supplier sync here"; exit 0; }
r=$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(cat /etc/patient/sync.token 2>/dev/null)" http://127.0.0.1:9090/feed 2>/dev/null)
echo "supplier answers $r; upstream $(systemctl is-active patient-upstream.service); patient-sync $(systemctl is-active patient-sync.service)"
[ "$r" = 200 ]
