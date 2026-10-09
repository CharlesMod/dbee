#!/bin/sh
# patient-web is moved to an unprivileged user (a drop-in, as an admin hardening
# the unit would), while its log dir stays root-owned: the service can no longer
# write its log and dies on it. Refused (exit 4) when the log dir is absent.
dir=/var/log/patient
m=/opt/dbee/.seeded-perms-log-dir
[ -d "$dir" ] || { echo "refused: no $dir on this patient"; exit 4; }
id nobody >/dev/null 2>&1 || { echo "refused: no user nobody"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /opt/dbee
echo "$(stat -c '%u:%g %a' "$dir") $(stat -c '%u:%g %a' "$dir/web.log" 2>/dev/null || echo none)" > "$m"
chown root:root "$dir"; chmod 0755 "$dir"
[ -e "$dir/web.log" ] && { chown root:root "$dir/web.log"; chmod 0644 "$dir/web.log"; }
mkdir -p /etc/systemd/system/patient-web.service.d
printf '[Service]\nUser=nobody\n' > /etc/systemd/system/patient-web.service.d/10-user.conf
systemctl daemon-reload
systemctl restart patient-web.service 2>/dev/null || true
sleep 4
echo "seeded: $dir $(stat -c '%U %a' "$dir"); patient-web $(systemctl is-active patient-web.service)"
