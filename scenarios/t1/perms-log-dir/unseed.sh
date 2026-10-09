#!/bin/sh
mkdir -p /run/.sim
# Return the patient: the drop-in goes, the log dir and file get their old owner and mode.
dir=/var/log/patient
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
read d_own d_mode f_own f_mode < "$m"
systemctl stop patient-web.service 2>/dev/null
rm -f /etc/systemd/system/patient-web.service.d/10-user.conf
rmdir /etc/systemd/system/patient-web.service.d 2>/dev/null
systemctl daemon-reload
chown "$d_own" "$dir"; chmod "$d_mode" "$dir"
[ "$f_own" != none ] && [ -e "$dir/web.log" ] && { chown "$f_own" "$dir/web.log"; chmod "$f_mode" "$dir/web.log"; }
rm -f "$m"
systemctl reset-failed patient-web.service 2>/dev/null
systemctl restart patient-web.service
sleep 2
echo "unseeded: $dir $(stat -c '%U %a' "$dir"); patient-web $(systemctl is-active patient-web.service)"
