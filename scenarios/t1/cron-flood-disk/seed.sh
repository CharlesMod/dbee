#!/bin/sh
# A cron entry that appends ~80 MB a minute to a log on the service's small log filesystem.
# Reads the log's own mount, never /. Refused (exit 4) when there is no log dir, no cron,
# or the log dir is already full. Waits for the cron job to fire and the service to fail.
dir=/var/log/patient
m=/opt/dbee/.seeded-cron-flood
[ -d "$dir" ] || { echo "refused: no $dir on this patient"; exit 4; }
[ -d /etc/cron.d ] && command -v cron >/dev/null || { echo "refused: no cron on this patient"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
avail_kb=$(df -Pk "$dir" | awk 'NR==2{print $4}')
[ "$avail_kb" -gt 1024 ] || { echo "refused: $dir already full"; exit 4; }
mkdir -p /opt/dbee; touch "$m"
cat > /etc/cron.d/patient-report <<'CRON'
# nightly report export, moved to every minute while testing
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
* * * * * root yes "report row $(date -Is) customer=acme status=ok total=1234.56" | head -c 80000000 >> /var/log/patient/report.log 2>/dev/null
CRON
chmod 644 /etc/cron.d/patient-report
systemctl start cron.service 2>/dev/null
for i in $(seq 1 85); do
    [ "$(systemctl is-active patient-web.service)" != active ] && break
    sleep 1
done
sleep 2
df -Ph "$dir" | sed 1d
echo "seeded: cron entry in place; report.log $(du -h $dir/report.log 2>/dev/null | cut -f1); patient-web $(systemctl is-active patient-web.service)"
