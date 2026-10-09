#!/bin/sh
# Return the Mac: the agents, their plists and the site go.
D="$HOME/Library/Application Support/PatientWeb"; L=com.example.patientweb; U=$(id -u)
PL="$HOME/Library/LaunchAgents/$L.plist"
[ -e "$D/.seeded" ] || { echo "nothing seeded here"; exit 0; }
launchctl bootout "gui/$U/com.example.preview" 2>/dev/null; rm -f "$HOME/Library/LaunchAgents/com.example.preview.plist"
launchctl bootout "gui/$U/$L" 2>/dev/null
rm -f "$PL"
rm -rf "$D"
echo "unseeded"
