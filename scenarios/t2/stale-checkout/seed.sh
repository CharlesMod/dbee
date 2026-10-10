#!/bin/sh
# The room's release (v2, takes --device) is laid in /opt/room-release, but the unit runs
# it as a module from /home/bee, where an old hand checkout of the same package (v1, no
# --device) sits; the working directory comes first on sys.path, so the old one wins
# (the fleet's fault of 2026-10-06: an old checkout beside the drone ran in its stead).
m=/run/.sim/seeded
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
command -v python3 >/dev/null || { echo "refused: no python3"; exit 4; }
mkdir -p /run/.sim /opt/room-release/room /home/bee/room; touch "$m"
: > /opt/room-release/room/__init__.py; : > /home/bee/room/__init__.py
cat > /opt/room-release/room/station.py <<'PY'
import argparse, http.server
a = argparse.ArgumentParser(); a.add_argument("--device", required=True); args = a.parse_args()
class Room(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"room: release 2 on {args.device}\n".encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
http.server.ThreadingHTTPServer(("127.0.0.1", 8090), Room).serve_forever()
PY
cat > /home/bee/room/station.py <<'PY'
import argparse, http.server
a = argparse.ArgumentParser(); args = a.parse_args()
class Room(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"room: release 1\n")
http.server.ThreadingHTTPServer(("127.0.0.1", 8090), Room).serve_forever()
PY
cat > /etc/systemd/system/patient-room.service <<'UNIT'
[Unit]
Description=the room's station
[Service]
Environment=PYTHONPATH=/opt/room-release
WorkingDirectory=/home/bee
ExecStart=/usr/bin/python3 -m room.station --device hw:0
Restart=no
UNIT
systemctl daemon-reload
systemctl start --no-block patient-room.service
sleep 2
echo "seeded: release 2 laid, old checkout in /home/bee/room; patient-room $(systemctl is-active patient-room.service)"
