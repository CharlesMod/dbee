#!/bin/sh
# HELD: a cgroup OOM kill in any container raises the host's /proc/vmstat oom_kill, which the
# hive's drone reads as its engine being killed, and it refuses the pin it serves for 6 h
# (swarm/drone/reconcile.go noteOOMKills). Seeding this on a frame that serves a model
# evicts that model. Refused until the drone counts only its own engine's kills, or the
# sim runs on a frame that serves nothing.
[ -z "$DBEE_ALLOW_HOST_OOM" ] && { echo "refused: a cgroup OOM here evicts the hive's served model (held)"; exit 4; }
# A batch unit capped at 20M whose job grows to ~40M: the cgroup OOM killer ends it.
# Wake note: the unit's own 'Failed with result oom-kill' line wakes the doctor (unit_failed);
# the kernel's OOM line is not relied on inside a container.
# Refused (exit 4) when python3 is missing or the cgroup has no memory controller.
m=/opt/dbee/.seeded-oom-service
command -v python3 >/dev/null || { echo "refused: no python3"; exit 4; }
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
mkdir -p /opt/dbee; touch "$m"
cat > /usr/local/bin/patient-batch <<'PY'
#!/usr/bin/python3
# the batch job: builds an in-memory table of ~40 MB, then serves from it
import os, time
ready = "/run/patient-batch.ready"
if os.path.exists(ready): os.remove(ready)
table = []
for i in range(40):
    table.append(bytearray(b"x" * 1024 * 1024))
    time.sleep(0.1)
open(ready, "w").write("ready\n")
while True:
    time.sleep(5)
PY
chmod +x /usr/local/bin/patient-batch
cat > /etc/systemd/system/patient-batch.service <<'UNIT'
[Unit]
Description=Patient batch: builds a table in memory and serves from it

[Service]
ExecStart=/usr/local/bin/patient-batch
MemoryMax=20M
MemorySwapMax=0
Restart=on-failure
RestartSec=8
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable patient-batch.service >/dev/null 2>&1
systemctl start --no-block patient-batch.service
sleep 6
echo "seeded: patient-batch $(systemctl is-active patient-batch.service) result=$(systemctl show -p Result --value patient-batch.service)"
