#!/bin/sh
# The mic probe: does the room's microphone record, and if not, whose fault is it.
# It records one second to nowhere through the audio server (the default device, as the station
# does), then straight from each capture card.
# Exit 2 (red, the audio-server fix's): the default will not open but a card records directly, so
# the user's audio server (PipeWire, PulseAudio) holds a stuck source.
# Exit 1 (red): nothing is plugged in to record from (every input jack the cards report reads off),
# or no capture card records either: a cable, the card or a mute only the keeper reaches.
# Exit 0: the default records, or the frame has no capture card at all.
# Read only: it changes nothing.
if command -v arecord >/dev/null 2>&1; then
  cards=$(arecord -l 2>/dev/null | sed -n 's/^card \([0-9]*\):.*device \([0-9]*\):.*/\1,\2/p')
  rec() { said=$(arecord -q -D "$1" -f S16_LE -r 16000 -c 1 -d 1 /dev/null 2>&1); }
elif command -v ffmpeg >/dev/null 2>&1; then
  cards=$(sed -n 's/^0*\([0-9][0-9]*\)-0*\([0-9][0-9]*\):.*capture.*/\1,\2/p' /proc/asound/pcm 2>/dev/null)
  rec() { said=$(ffmpeg -hide_banner -loglevel error -nostdin -f alsa -i "$1" -t 1 -f null - 2>&1); }
else
  echo "GREEN: no arecord and no ffmpeg on this frame: nothing here records a room"; exit 0
fi
[ -n "$cards" ] || { echo "GREEN: no capture card on this frame"; exit 0; }
if rec default; then echo "GREEN: the default device records a second"; exit 0; fi
why=$(printf '%s\n' "$said" | grep -iE 'error|unable|cannot' | head -1); [ -n "$why" ] || why=$(printf '%s' "$said" | tail -1)
# A card's input jacks (a mic jack, a line-in) as its controls say: all off is nothing plugged in.
jacks() { amixer -c "${1%%,*}" contents 2>/dev/null | awk '
  /name=/ { n = $0; sub(/.*name=./, "", n); sub(/.$/, "", n)
            inp = (n ~ / Jack$/) && (n ~ /Mic/ || (n ~ /Line/ && n !~ /Out/)); next }
  inp && /: values=/ { seen++; if ($0 !~ /values=off/) on++; inp = 0 }
  END { if (!seen) print "none"; else if (on) print "plugged"; else print "empty" }'; }
if command -v amixer >/dev/null 2>&1; then
  empty=1
  for c in $cards; do [ "$(jacks "$c")" = empty ] || empty=0; done
  if [ $empty = 1 ]; then
    echo "RED: nothing is plugged in to record from: every input jack on $(echo $cards) reads off (the default says: $why); the keeper plugs a mic in, or unchecks this frame's mic"
    exit 1
  fi
fi
ok=""
for c in $cards; do rec "plughw:$c" && ok="$ok plughw:$c"; done
if [ -n "$ok" ]; then
  echo "RED: the default device will not record ($why) but the card records directly ($ok): the user's audio server holds a stuck source"
  exit 2
fi
echo "RED: neither the default device ($why) nor any capture card ($(echo $cards)) records"
exit 1
