#!/bin/sh
mkdir -p /run/.sim
# Return the box: the hand-run court ended (its pid proven by its command line), the unit's court serving.
m=/run/.sim/seeded
[ -e "$m" ] || { echo "nothing seeded here"; exit 0; }
for p in $(pgrep -x court); do
    tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q -- '--db /tmp/court-try.db' && kill $p
done
for i in $(seq 40); do ss -ltn | grep -q '127.0.0.1:4410 ' || break; sleep 0.25; done
rm -f /tmp/court-try.db /tmp/court-try.db-* /tmp/court-try.log
systemctl reset-failed hive-court.service 2>/dev/null
systemctl restart hive-court.service
rm -f "$m"
sleep 1
echo "unseeded: hive-court $(systemctl is-active hive-court.service)"
