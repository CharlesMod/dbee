#!/bin/sh
# The no-linger drill's seed: this account stops lingering, so the drone's user unit would not
# start after a reboot and the drone says noboot on its next advertisement. The value it had is
# kept first under the drills folder, for the unseed. Refused (exit 4, nothing changed) where the
# fault cannot be seeded safely: the drone is not this account's user unit (linger does not
# decide its boot), or the account has no login session (logind stops a user manager that
# neither lingers nor has a session, and the drone with it).
u=$(id -un)
dir="${HIVE_HOME:-$HOME/.hive}/drills"
state="$dir/no-linger.linger"
was=$(loginctl show-user "$u" -p Linger --value 2>/dev/null)
if [ "$was" != yes ]; then
    echo "refused: $u does not linger already (Linger=${was:-unknown}): nothing to seed"
    exit 4
fi
if ! grep -q "user@" /proc/self/cgroup 2>/dev/null; then
    echo "refused: the drone here is not $u's user unit, so linger does not decide its boot"
    exit 4
fi
if [ -z "$(loginctl show-user "$u" -p Sessions --value 2>/dev/null)" ]; then
    echo "refused: $u has no login session; with linger off logind would stop the user manager and the drone with it"
    exit 4
fi
mkdir -p "$dir" || exit 1
[ -e "$state" ] || echo "$was" > "$state" || exit 1
loginctl disable-linger "$u" 2>/dev/null || sudo -n loginctl disable-linger "$u" || exit 1
echo "seeded: linger for $u: $(loginctl show-user "$u" -p Linger --value)"
