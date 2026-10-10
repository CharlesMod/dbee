#!/bin/sh
# Return the patient: the account, its user manager and its linger go.
id bee >/dev/null 2>&1 || { echo "nothing seeded here"; exit 0; }
loginctl disable-linger bee 2>/dev/null
systemctl stop "user@$(id -u bee).service" 2>/dev/null
userdel -r bee 2>/dev/null
rm -f /var/lib/systemd/linger/bee
echo "unseeded"
