#!/bin/sh
# a cleanup moved the agent's script to bin.old, so launchd cannot start what its plist names.
# Everything lives in the user's own domain: one LaunchAgent and its folder. Refused (exit 4) when
# python3 is missing, the label is loaded already or 18080 is taken.
D="$HOME/Library/Application Support/PatientWeb"; L=com.example.patientweb; U=$(id -u)
PL="$HOME/Library/LaunchAgents/$L.plist"
m="$D/.seeded"
command -v python3 >/dev/null && python3 -c 1 2>/dev/null || { echo "refused: no python3"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
launchctl print "gui/$U/$L" >/dev/null 2>&1 && { echo "refused: $L is already loaded"; exit 4; }
lsof -nP -iTCP:18080 -sTCP:LISTEN >/dev/null 2>&1 && { echo "refused: 18080 is taken before the seed"; exit 4; }
# the patient: a small site served by a user LaunchAgent, as a developer's Mac would run one
mkdir -p "$D/site" "$D/bin" "$HOME/Library/LaunchAgents"; touch "$m"
echo "<h1>patient</h1>" > "$D/site/index.html"
printf 'port=18080\n' > "$D/patient.conf"
cat > "$D/bin/web.sh" <<'SH'
#!/bin/sh
# patient-web: serves the site on the port its config names.
D="$HOME/Library/Application Support/PatientWeb"
port=$(sed -n 's/^port=//p' "$D/patient.conf")
[ -n "$port" ] || { echo "patient-web: cannot read a port from $D/patient.conf" >&2; exit 1; }
exec /usr/bin/python3 -m http.server "$port" --bind 127.0.0.1 --directory "$D/site"
SH
chmod 755 "$D/bin/web.sh"
cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>$L</string>
<key>ProgramArguments</key><array><string>$D/bin/web.sh</string></array>
<key>KeepAlive</key><true/>
<key>ThrottleInterval</key><integer>5</integer>
<key>StandardErrorPath</key><string>$D/web.err.log</string>
</dict></plist>
PLIST
up() { for i in 1 2 3 4 5 6 7 8 9 10 11 12; do [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:18080/)" = 200 ] && return 0; sleep 0.5; done; return 1; }
launchctl bootstrap "gui/$U" "$PL" || { echo "refused: bootstrap failed"; exit 4; }
up || { echo "refused: the patient did not come up"; exit 4; }
mkdir -p "$D/bin.old"; mv "$D/bin/web.sh" "$D/bin.old/web.sh"
launchctl kickstart -k "gui/$U/$L"
sleep 3
echo "seeded: web.sh moved to bin.old; $L $(launchctl print "gui/$U/$L" | sed -n 's/^[[:space:]]*state = //p' | head -1)"
