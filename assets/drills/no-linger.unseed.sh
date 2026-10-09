#!/bin/sh
# The no-linger drill's unseed: linger goes back to the value the seed kept. Safe to run twice
# and after a seed that stopped part way: with nothing kept it changes nothing.
u=$(id -un)
state="${HIVE_HOME:-$HOME/.hive}/drills/no-linger.linger"
if [ ! -e "$state" ]; then
    echo "nothing seeded here: linger for $u: $(loginctl show-user "$u" -p Linger --value 2>/dev/null)"
    exit 0
fi
if [ "$(cat "$state")" = yes ]; then
    loginctl enable-linger "$u" 2>/dev/null || sudo -n loginctl enable-linger "$u" || exit 1
fi
rm -f "$state"
echo "restored: linger for $u: $(loginctl show-user "$u" -p Linger --value 2>/dev/null)"
