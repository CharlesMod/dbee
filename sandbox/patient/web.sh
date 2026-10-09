#!/bin/sh
# patient-web: serves the site on :8080 and logs a heartbeat every second.
set -u
log=/var/log/patient/web.log
mkdir -p /var/log/patient /srv/patient
[ -e /srv/patient/index.html ] || echo "<h1>patient</h1>" > /srv/patient/index.html
cd /srv/patient || exit 1
python3 -m http.server 8080 --bind 127.0.0.1 >/dev/null 2>&1 &
srv=$!
trap 'kill $srv 2>/dev/null; exit 0' TERM INT
while kill -0 $srv 2>/dev/null; do
    echo "$(date -Is) web alive pid $srv" >> "$log" || { echo "log write failed: $?" >&2; kill $srv; exit 1; }
    sleep 1
done
exit 1
