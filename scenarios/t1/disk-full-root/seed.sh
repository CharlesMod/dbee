#!/bin/sh
mkdir -p /run/.sim
# Fill the filesystem that holds the service's log with the service's own log,
# until its next write fails and the service dies on it. Reads the log's own
# mount, never /, so a patient whose log dir is a small volume fills that and
# nothing else. Refused (exit 4) when the log directory is not where the
# patient lays it.
log=/var/log/patient/web.log
dir=$(dirname "$log")
[ -d "$dir" ] || { echo "refused: no $dir on this patient"; exit 4; }
touch "/run/.sim/seeded"
avail_kb=$(df -Pk "$dir" | awk 'NR==2{print $4}')
fill_kb=$((avail_kb - 256))
[ "$fill_kb" -gt 0 ] || { echo "refused: $dir already full"; exit 4; }
fallocate -l "${fill_kb}K" "$log" 2>/dev/null || dd if=/dev/zero of="$log" bs=1K count="$fill_kb" status=none 2>/dev/null
# the service writes a line a second: the next ones hit ENOSPC
dd if=/dev/zero of="$dir/web.log.1" bs=1K count=1024 status=none 2>/dev/null   # take the last of it
systemctl restart patient-web.service 2>/dev/null || true
sleep 4
df -Ph "$dir" | sed 1d
echo "seeded: $log at $(du -h "$log" | cut -f1); patient-web $(systemctl is-active patient-web.service)"
