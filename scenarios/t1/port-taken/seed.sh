#!/bin/sh
# Another process takes 127.0.0.1:8080 while patient-web is down, then patient-web
# is started and cannot bind. Refused (exit 4) when nothing is listening there to begin with
# (the patient is not in its ordinary state) or python3 is missing.
m=/opt/dbee/.seeded-port-taken
command -v python3 >/dev/null || { echo "refused: no python3"; exit 4; }
systemctl is-active --quiet patient-web.service || { echo "refused: patient-web is not running to begin with"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /opt/dbee; touch "$m"
systemctl stop patient-web.service
for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltn 'sport = :8080' | grep -q LISTEN || break; sleep 0.5; done
systemd-run --quiet --unit=preview-http --description="Preview of the new site" \
    python3 -m http.server 8080 --bind 127.0.0.1 --directory /tmp
sleep 1
systemctl start --no-block patient-web.service
sleep 4
echo "seeded: 8080 held by $(systemctl show -p MainPID --value preview-http.service); patient-web $(systemctl is-active patient-web.service)"
