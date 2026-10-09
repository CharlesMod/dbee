#!/bin/sh
# Return the patient: the cron entry and the log go, the service is reset and started.
dir=/var/log/patient
m=/opt/dbee/.seeded-cron-flood
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
rm -f /etc/cron.d/patient-report /etc/cron.d/patient-report.* /etc/cron.d/.patient-report*
sleep 1
pkill -x yes 2>/dev/null
rm -f "$dir/report.log"
: > "$dir/web.log"
rm -f "$m"
systemctl reset-failed patient-web.service 2>/dev/null
systemctl restart patient-web.service
sleep 2
echo "unseeded: $(df -Ph "$dir" | awk 'NR==2{print $5}') used; patient-web $(systemctl is-active patient-web.service)"
