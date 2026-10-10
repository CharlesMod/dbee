#!/bin/sh
# Healthy: no drone account here, or the account lingers (its user manager, and the drone with
# it, starts at boot and survives a logout) and the drone answers.
id bee >/dev/null 2>&1 || { echo "no drone account here"; exit 0; }
l=no; [ -e /var/lib/systemd/linger/bee ] && l=yes
code=$(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:4411/)
echo "bee lingers: $l; drone :4411 http $code"
[ "$l" = yes ] && [ "$code" = 200 ]
