#!/bin/sh
mkdir -p /run/.sim
# Return the patient: nginx stopped and disabled again, the new conf (or its moved-aside copy) gone.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
systemctl stop nginx.service 2>/dev/null
systemctl disable nginx.service >/dev/null 2>&1
systemctl reset-failed nginx.service 2>/dev/null
rm -f /etc/nginx/conf.d/patient-proxy.conf* /etc/nginx/patient-proxy.conf* /root/patient-proxy.conf* /tmp/patient-proxy.conf*
rm -f "$m"
echo "unseeded: nginx $(systemctl is-active nginx.service), $(systemctl is-enabled nginx.service 2>&1)"
