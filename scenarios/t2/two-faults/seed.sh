#!/bin/sh
# Two faults at once: a preview server took 127.0.0.1:8080, and patient-web was moved to
# an unprivileged user while its log dir stayed root-owned. Curing either alone leaves
# the service failing on the other. Refused (exit 4) when patient-web is not running to
# begin with, the log dir is absent, or there is no user nobody.
m=/run/.sim/seeded
dir=/var/log/patient
command -v python3 >/dev/null || { echo "refused: no python3"; exit 4; }
systemctl is-active --quiet patient-web.service || { echo "refused: patient-web is not running to begin with"; exit 4; }
[ -d "$dir" ] || { echo "refused: no $dir"; exit 4; }
id nobody >/dev/null 2>&1 || { echo "refused: no user nobody"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /run/.sim; touch "$m"
systemctl stop patient-web.service
for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltn 'sport = :8080' | grep -q LISTEN || break; sleep 0.5; done
systemd-run --quiet --unit=preview-http --description="Preview of the new site" \
    python3 -m http.server 8080 --bind 127.0.0.1 --directory /tmp
chown root:root "$dir"; chmod 0755 "$dir"
[ -e "$dir/web.log" ] && { chown root:root "$dir/web.log"; chmod 0644 "$dir/web.log"; }
mkdir -p /etc/systemd/system/patient-web.service.d
printf '[Service]\nUser=nobody\n' > /etc/systemd/system/patient-web.service.d/10-user.conf
systemctl daemon-reload
sleep 1
systemctl start --no-block patient-web.service
sleep 4
echo "seeded: 8080 held by preview-http; $dir $(stat -c '%U %a' "$dir"); patient-web runs as nobody, $(systemctl is-active patient-web.service)"
