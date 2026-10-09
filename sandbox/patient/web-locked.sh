#!/bin/sh
# patient-web behind a lock file: refuses to start when the lock exists, the way
# a naive single-instance guard does; removes its lock when it stops.
lock=/run/patient/web.lock
mkdir -p /run/patient
if [ -e "$lock" ]; then
    echo "patient-web: lock $lock exists (held by pid $(cat "$lock" 2>/dev/null)); refusing to start" >&2
    exit 1
fi
echo $$ > "$lock"
/opt/patient/web.sh &
child=$!
trap 'kill $child 2>/dev/null; rm -f "$lock"; exit 0' TERM INT
wait $child
rc=$?
rm -f "$lock"
exit $rc
