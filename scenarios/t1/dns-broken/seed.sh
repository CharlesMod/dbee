#!/bin/sh
# resolv.conf is pointed at a nameserver nobody answers; patient-fetch (installed here) fails on it.
# The original is kept aside as resolv.conf.held. Refused (exit 4) when there is no resolv.conf.
m=/run/.sim/seeded
[ -e /etc/resolv.conf ] || { echo "refused: no /etc/resolv.conf"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /run/.sim; touch "$m"
cp -p /etc/resolv.conf /etc/resolv.conf.held
# written in place: resolv.conf may be a bind mount that cannot be renamed over
printf 'nameserver 192.0.2.1\noptions timeout:1 attempts:1\n' > /etc/resolv.conf
cat > /etc/systemd/system/patient-fetch.service <<'UNIT'
[Unit]
Description=Patient fetch: pull the day's file from the upstream host

[Service]
Type=oneshot
ExecStart=/usr/bin/curl -fsS --max-time 8 -o /dev/null http://updates.example.com/daily
UNIT
systemctl daemon-reload
systemctl start --no-block patient-fetch.service
for i in $(seq 1 30); do [ "$(systemctl is-active patient-fetch.service)" = activating ] || break; sleep 1; done
echo "seeded: resolv.conf -> $(grep nameserver /etc/resolv.conf); patient-fetch $(systemctl is-active patient-fetch.service)"
