#!/bin/sh
# Restart the user's audio server (PipeWire and its session manager, or PulseAudio), so it opens
# its cards afresh: a source it holds stuck opens again. Streams playing drop for a moment.
units=""
for u in wireplumber pipewire pipewire-pulse pulseaudio; do
  [ "$(systemctl --user is-active "$u" 2>/dev/null)" = active ] && units="$units $u"
done
[ -n "$units" ] || { echo "no user audio server runs here"; exit 1; }
systemctl --user restart $units || exit 1
echo "restarted:$units"
