#!/bin/sh
# A deploy repointed /srv/patient at a release that was never unpacked (a dangling
# symlink), so patient-web cannot enter its site and dies; meanwhile a loud probe that
# has nothing to do with it fills the journal and the web log with database and
# out-of-memory errors. Refused (exit 4) when /srv/patient is not a plain directory.
m=/run/.sim/seeded
{ [ -d /srv/patient ] && [ ! -L /srv/patient ]; } || { echo "refused: /srv/patient is not a plain directory"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /run/.sim /srv/releases; touch "$m"
systemctl stop patient-web.service
mv /srv/patient /srv/releases/2026-10-07
echo "<h1>patient</h1><!-- release 2026-10-07 -->" > /srv/releases/2026-10-07/index.html
ln -s /srv/releases/2026-10-09 /srv/patient
systemd-run --quiet --unit=patient-db-probe --description="Database reachability probe" sh -c \
  'while :; do echo "ERROR db: connection to 10.20.0.5:5432 refused; is the database down?" >&2
   echo "$(date -Is) ERROR worker: out of memory, request dropped (db pool exhausted)" >> /var/log/patient/web.log
   sleep 2; done'
systemctl start --no-block patient-web.service
sleep 4
echo "seeded: /srv/patient -> $(readlink /srv/patient) (absent); patient-web $(systemctl is-active patient-web.service); probe $(systemctl is-active patient-db-probe.service)"
