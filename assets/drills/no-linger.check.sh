#!/bin/sh
# The no-linger drill's check: exit 0 when this account lingers (logind keeps its user manager
# running, so the drone's user unit starts at boot), 1 when it does not.
u=$(id -un)
linger=$(loginctl show-user "$u" -p Linger --value 2>/dev/null)
[ -z "$linger" ] && [ -e "/var/lib/systemd/linger/$u" ] && linger=yes
echo "linger for $u: ${linger:-unknown}"
[ "$linger" = yes ]
