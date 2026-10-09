#!/bin/sh
# The linger fix undone: logind no longer keeps this account's user manager running when nobody is logged in.
u=$(id -un)
loginctl disable-linger "$u" 2>/dev/null || sudo -n loginctl disable-linger "$u" || exit 1
echo "linger for $u: $(loginctl show-user "$u" -p Linger --value)"
