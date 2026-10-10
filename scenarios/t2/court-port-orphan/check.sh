#!/bin/sh
# Healthy: the court's unit is active and it is the unit's own process that holds :4410
# and answers (a court run by hand on the port is not the court).
a=$(systemctl is-active hive-court.service 2>/dev/null)
main=$(systemctl show -p MainPID --value hive-court.service 2>/dev/null)
holder=$(ss -ltnpH 'sport = :4410' 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:4410/v1/drones 2>/dev/null)
echo "hive-court $a (MainPID ${main:-none}); :4410 held by pid ${holder:-none}; /v1/drones $code"
[ "$a" = active ] && [ -n "$holder" ] && [ "$holder" = "$main" ] && [ "$code" = 200 ]
