#!/bin/sh
# The lastboot probe: how this frame's previous boot ended, read from its own journal, for an
# outage nobody on the frame could see while it lasted (the Queen's own dark spell).
# Exit 1 (red): the boot before ended without a clean shutdown (no shutdown target or
# systemd-shutdown near its end): it froze, lost power or was reset. Exit 0: it shut down
# cleanly, or no journal here holds it (it says which). Read only: it changes nothing. It prints the
# verdict first, then the boots listed, the last 30 lines of the boot before and the kernel's
# warnings from it that name a cause.
if ! command -v journalctl >/dev/null 2>&1; then
  echo "UNKNOWN: no journalctl on this frame: its boots cannot be read here"
  exit 0
fi
boots=$(journalctl --list-boots --no-pager 2>/dev/null | tail -3)
end=$(journalctl -b -1 -n 30 --no-pager -o short-iso 2>/dev/null | tail -30)
kern=$(journalctl -k -b -1 -p warning --no-pager -o short-iso 2>/dev/null \
  | grep -iE "oom|out of memory|lockup|hung|mce|machine check|watchdog|nvme|i/o error|thermal" | tail -20)
if [ -z "$end" ]; then
  echo "UNKNOWN: the journal holds no boot before this one (it is not kept across boots here)"
  echo "== boots"; echo "$boots"
  exit 0
fi
if printf '%s\n' "$end" | grep -qE "Reached target .*(Shutdown|Power.?Off|Reboot|Halt)|systemd-shutdown|System is (powering down|rebooting)|Journal stopped"; then
  echo "GREEN: the boot before shut down cleanly (a reboot or power-off someone or something asked for)"
  code=0
else
  echo "RED: the boot before ended without a clean shutdown: it froze, lost power or was reset"
  code=1
fi
echo "== boots"
echo "$boots"
echo "== the last 30 lines of the boot before"
echo "$end"
if [ -n "$kern" ]; then
  echo "== the kernel's warnings in the boot before"
  echo "$kern"
else
  echo "== the kernel said no warning naming oom, lockup, hung task, mce, watchdog, nvme, I/O error or thermal"
fi
exit $code
