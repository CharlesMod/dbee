#!/bin/sh
# The audio-server fix undone: a restart leaves nothing to put back; the server runs as it did,
# and this says so.
for u in wireplumber pipewire pipewire-pulse pulseaudio; do
  s=$(systemctl --user is-active "$u" 2>/dev/null) && echo "$u: $s"
done
exit 0
