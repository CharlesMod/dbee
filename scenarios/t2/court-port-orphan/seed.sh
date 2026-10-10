#!/bin/sh
# A court started by hand to try something, outside its unit, is left running on the
# court's own port; the court's unit restarts and cannot bind. The hand-run one answers
# in its place with a throwaway database (the fleet's fault of 2026-10-06 in another
# shape: a child a previous run left holding a port, every start of the new one refused).
m=/run/.sim/seeded
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
systemctl is-active -q hive-court.service || { echo "refused: no court in this box"; exit 4; }
mkdir -p /run/.sim; touch "$m"
systemctl stop hive-court.service
HIVE_TRUST=off setsid /usr/local/bin/court serve --db /tmp/court-try.db --listen 127.0.0.1:4410 >/tmp/court-try.log 2>&1 < /dev/null &
for i in $(seq 40); do curl -s --max-time 1 -o /dev/null http://127.0.0.1:4410/v1/drones && break; sleep 0.25; done
systemctl start --no-block hive-court.service
sleep 2
echo "seeded: a hand-run court holds :4410; hive-court $(systemctl is-active hive-court.service)"
