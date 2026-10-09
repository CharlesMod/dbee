#!/bin/sh
# Ask logind to keep this account's user manager running, so the drone's user unit starts at boot
# and survives a logout. A polkit rule may want root: passwordless sudo is the keeper's standing word.
u=$(id -un)
loginctl enable-linger "$u" 2>/dev/null || sudo -n loginctl enable-linger "$u" || exit 1
echo "linger for $u: $(loginctl show-user "$u" -p Linger --value)"
