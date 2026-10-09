#!/bin/sh
# patient-web is replaced by its single-instance-guarded form (copied from /opt/patient),
# and a lock holding a dead pid is left behind. Refused (exit 4) when the fixtures are missing.
m=/run/.sim/seeded
for f in web-locked.sh patient-web-locked.service; do
    [ -e /opt/patient/$f ] || { echo "refused: /opt/patient/$f missing"; exit 4; }
done
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /run/.sim /run/patient; touch "$m"
cp /opt/patient/patient-web-locked.service /etc/systemd/system/
pid=424242; while kill -0 $pid 2>/dev/null; do pid=$((pid+1)); done
echo $pid > /run/patient/web.lock
systemctl daemon-reload
systemctl stop patient-web.service
systemctl start --no-block patient-web-locked.service
sleep 4
echo "seeded: lock holds dead pid $pid; patient-web-locked $(systemctl is-active patient-web-locked.service)"
