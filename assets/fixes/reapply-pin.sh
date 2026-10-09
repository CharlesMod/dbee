#!/bin/sh
# reapply-pin: the drone says a pin is applied, but its engine is gone. The drone sets its
# record aside (moved, never deleted; `drone pin set-aside` refuses while the engine is
# provably alive), so its own serve reconcile finds its standing order (a held role or the
# court's config) with nothing applied, and applies it again: engine, probe and
# advertisement, by the one path a serve order takes. Undo: reapply-pin.undo.sh.
D="${HIVE_DRONE:-${HIVE_HOME:-$HOME/.hive}/bin/drone}"
port=$("$D" pin show | python3 -c 'import json,sys; print(json.load(sys.stdin).get("port") or 4411)')
listening() { [ -n "$(ss -ltnH "sport = :$port")" ]; }
if listening; then
    echo "something listens on :$port: this fix is for a dead engine, and changes nothing"
    exit 4
fi
"$D" pin set-aside || exit $?
i=0
while [ $i -lt 60 ]; do
    i=$((i + 1))
    sleep 2
    if "$D" pin show | grep -q '"applied":true' && listening; then
        echo "the drone applied its order again: a new record, and :$port listens after $((i * 2)) s"
        exit 0
    fi
done
echo "after 120 s: :$port is $(listening && echo listening || echo silent)"
exit 1
