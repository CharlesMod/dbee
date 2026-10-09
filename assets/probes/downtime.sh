#!/bin/sh
# The downtime probe: why this frame's drone went down, read on the frame once it is back, and
# whether it will start again by itself next time.
# Exit 1 (red): the drone runs as the user's own unit and the account does not linger, so after a
# reboot (or a logout) nothing starts it until someone logs in (the linger fix answers it).
# Exit 3 (red, not linger's): it will not start by itself for another reason: a Mac
# LaunchAgent, a unit nobody enabled. A WSL distro's boot task is said as a fact, never a red:
# its stamp is written only by an unattended raise. Exit 0: it will start
# by itself, and the tail says what it read. It reads what the drone's boot cap reads (boot.go).
# Read only: it changes nothing. It prints the verdict first, then the facts it rests on.
facts=""
say() { facts="$facts
$1"; }
boot=$(uptime -s 2>/dev/null)
[ -n "$boot" ] && boot="$boot $(date +%Z)"
[ -n "$boot" ] && say "this boot began at $boot"
if command -v journalctl >/dev/null 2>&1; then
  last=$(journalctl -b -1 -n 1 --no-pager -o short-iso 2>/dev/null | tail -1)
  [ -n "$last" ] && say "the boot before ended with: $last"
  if journalctl -b -1 --no-pager 2>/dev/null | grep -qE "Reached target .*(Shutdown|Power.?Off|Reboot)|systemd-shutdown|System is (powering down|rebooting)|Journal stopped"; then
    say "the boot before shut down cleanly (a reboot or power-off someone or something asked for)"
  elif [ -n "$last" ]; then
    say "the boot before has no shutdown in its journal: it stopped abruptly (power lost, a hang, a hard reset)"
  fi
  oom=$(journalctl -k -b -1 --no-pager 2>/dev/null | grep -iE "out of memory|oom-kill|killed process" | tail -3)
  [ -n "$oom" ] && say "the kernel killed for memory in the boot before:
$oom"
fi
unit=""
grep -q "user@" /proc/self/cgroup 2>/dev/null && unit=user
[ -z "$unit" ] && grep -q "hive-drone" /proc/self/cgroup 2>/dev/null && unit=system
say "the drone runs as $(id -un) (uid $(id -u)), $([ -n "$unit" ] && echo "a $unit unit" || echo "under no systemd unit")"
if [ "$unit" = user ] && command -v systemctl >/dev/null 2>&1; then
  st=$(systemctl --user show hive-drone -p ActiveEnterTimestamp -p NRestarts -p UnitFileState 2>/dev/null | tr '\n' ' ')
  say "the drone is the user's unit hive-drone: $st"
fi
if grep -qi microsoft /proc/version 2>/dev/null; then
  if [ -e /var/lib/hive/wsl-boot ]; then
    say "this WSL distro was raised at boot by its Windows host's boot task"
  else
    say "this WSL distro has never been raised by a boot task: either its Windows host has none (the keeper approves the tray's boot task once) or it has not restarted since one was registered"
  fi
fi
if [ "$(uname -s)" = Darwin ]; then
  if [ -e /Library/LaunchDaemons/com.hive.drone.plist ]; then
    echo "GREEN: the drone is a LaunchDaemon: it starts at boot by itself$facts"; exit 0
  fi
  if [ -e "$HOME/Library/LaunchAgents/com.hive.drone.plist" ]; then
    echo "RED: the drone is a LaunchAgent: it starts only when $(id -un) logs in, which FileVault never does unattended (fix: the keeper joins again with sudo, which writes a LaunchDaemon)$facts"
    exit 3
  fi
fi
if [ "$unit" = system ] && command -v systemctl >/dev/null 2>&1 && \
   [ "$(systemctl is-enabled hive-drone 2>/dev/null)" != enabled ]; then
  echo "RED: the drone is a system unit nobody enabled: nothing starts it at boot (fix: systemctl enable hive-drone, as root)$facts"
  exit 3
fi
if [ "$unit" = user ] && command -v systemctl >/dev/null 2>&1 && \
   [ "$(systemctl --user is-enabled hive-drone 2>/dev/null)" != enabled ]; then
  echo "RED: the drone is $(id -un)'s own unit and nobody enabled it: nothing starts it at boot (fix: systemctl --user enable hive-drone)$facts"
  exit 3
fi
linger=$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)
if [ "$unit" = user ] && [ "$linger" != "yes" ]; then
  echo "RED: the drone is $(id -un)'s own unit and the account does not linger: after a reboot or a logout nothing starts it until someone logs in (fix: linger)$facts"
  exit 1
fi
case "$unit" in
  user) echo "GREEN: the drone is $(id -un)'s own unit and the account lingers: it starts at boot by itself$facts" ;;
  system) echo "GREEN: the drone is a system unit: it starts at boot by itself$facts" ;;
  *) echo "GREEN: the drone is not a systemd unit here (linger does not apply): what starts it is the platform's own$facts" ;;
esac
exit 0
