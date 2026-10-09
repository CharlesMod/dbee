#!/bin/sh
mkdir -p /run/.sim
# Return the patient: nginx stopped and disabled, the cert, its trust entry, the conf and the unit gone.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop nginx.service patient-fetch.service 2>/dev/null
systemctl disable nginx.service >/dev/null 2>&1
rm -f /etc/nginx/conf.d/patient-tls.conf* /etc/systemd/system/patient-fetch.service /usr/local/share/ca-certificates/patient.crt
rm -rf /etc/ssl/patient
update-ca-certificates --fresh >/dev/null 2>&1
systemctl daemon-reload
systemctl reset-failed nginx.service patient-fetch.service 2>/dev/null
rm -f "$m"
echo "unseeded: nginx $(systemctl is-active nginx.service)"
