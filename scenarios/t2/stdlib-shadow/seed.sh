#!/bin/sh
# A release of the room's app lays its own module app/operator.py; the unit runs the
# app as a script path, so the module shadows the standard library's operator and the
# room cannot start (the fleet's fault of 2026-10-06, every room refused its station).
m=/run/.sim/seeded
[ -e "$m" ] && { echo "refused: already seeded"; exit 4; }
command -v python3 >/dev/null || { echo "refused: no python3"; exit 4; }
mkdir -p /run/.sim /opt/room/app; touch "$m"
: > /opt/room/app/__init__.py
cat > /opt/room/app/operator.py <<'PY'
"""The room's operator: who is at the desk."""
def who():
    return "the operator"
PY
cat > /opt/room/app/station.py <<'PY'
import http.server
from app.operator import who
class Room(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"room: {who()} answers\n".encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
http.server.ThreadingHTTPServer(("127.0.0.1", 8090), Room).serve_forever()
PY
cat > /etc/systemd/system/patient-room.service <<'UNIT'
[Unit]
Description=the room's station
[Service]
Environment=PYTHONPATH=/opt/room
ExecStart=/usr/bin/python3 /opt/room/app/station.py
Restart=no
UNIT
systemctl daemon-reload
systemctl start --no-block patient-room.service
sleep 2
echo "seeded: release with app/operator.py laid; patient-room $(systemctl is-active patient-room.service)"
