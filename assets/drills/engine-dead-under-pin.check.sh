#!/bin/sh
# The engine-dead-under-pin drill's check: exit 0 when the drone says a pin is applied and
# something answers HTTP on its port (/health or /v1/models), 1 when no pin is applied or
# nothing answers.
D="${HIVE_DRONE:-${HIVE_HOME:-$HOME/.hive}/bin/drone}"
shown=$("$D" pin show 2>/dev/null)
echo "drone pin show: ${shown:-nothing}"
port=$(printf '%s' "$shown" | python3 -c 'import json, sys
d = json.load(sys.stdin)
print((d.get("port") or "") if d.get("applied") else "")' 2>/dev/null)
[ -n "$port" ] || { echo "no applied pin"; exit 1; }
for path in /health /v1/models; do
    if python3 -c 'import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=5).read(1)' "http://127.0.0.1:$port$path" 2>/dev/null; then
        echo "GET :$port$path answers"
        exit 0
    fi
done
echo "nothing answers on :$port"
exit 1
