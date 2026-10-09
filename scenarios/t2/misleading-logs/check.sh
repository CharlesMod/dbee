#!/bin/sh
# Healthy: patient-web runs and serves its site; on a patient with releases, the site
# served is the release that was deployed (the 2026-10-07 page), not an empty directory
# made to quiet the error.
active=$(systemctl is-active patient-web.service)
page=$(curl -s --max-time 3 http://127.0.0.1:8080/ 2>/dev/null)
want="<h1>patient</h1>"; [ -d /srv/releases ] && want="release 2026-10-07"
echo "/srv/patient -> $(readlink -f /srv/patient 2>/dev/null || echo none); patient-web $active; page: $(echo "$page" | head -c 80)"
[ "$active" = active ] && echo "$page" | grep -q "$want"
