#!/bin/sh
# Healthy: no patient web here, or its own agent (not a squatter) holds 18080 and answers.
D="$HOME/Library/Application Support/PatientWeb"; L=com.example.patientweb; U=$(id -u)
PL="$HOME/Library/LaunchAgents/$L.plist"
launchctl print "gui/$U/$L" >/dev/null 2>&1 || { echo "no patient web here"; exit 0; }
st=$(launchctl print "gui/$U/$L" | sed -n 's/^[[:space:]]*state = //p' | head -1)
pid=$(launchctl print "gui/$U/$L" | sed -n 's/^[[:space:]]*pid = //p' | head -1)
lp=$(lsof -nP -iTCP:18080 -sTCP:LISTEN -t 2>/dev/null | head -1)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:18080/)
echo "$L $st pid ${pid:-none}; 18080 held by ${lp:-nobody}; http $code"
[ "$st" = running ] && [ -n "$pid" ] && [ "$pid" = "$lp" ] && [ "$code" = 200 ]
