#!/bin/sh
# The Hive's recorded fault (drone-no-linger, 2026-10-04): the drone runs as its account's own
# user unit; the account stopped lingering, and when its user manager went down (a logout, a
# reboot) nothing started it again. The machine is up and the drone is dark. Refused (exit 4)
# where logind cannot linger or the account exists already.
id bee >/dev/null 2>&1 && { echo "refused: bee exists already"; exit 4; }
command -v loginctl >/dev/null && command -v python3 >/dev/null || { echo "refused: no loginctl or python3"; exit 4; }
useradd -m -s /bin/sh bee || { echo "refused: useradd failed"; exit 4; }
U=$(id -u bee); H=/home/bee
mkdir -p "$H/.config/systemd/user/default.target.wants" "$H/.hive"
cat > "$H/.hive/drone.py" <<'PY'
# the frame's worker: it answers its advertisement on :4411
import http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"node": "bee", "ok": true}')
    def log_message(self, *a):
        pass
http.server.HTTPServer(("127.0.0.1", 4411), H).serve_forever()
PY
cat > "$H/.config/systemd/user/hive-drone.service" <<'UNIT'
[Unit]
Description=hive drone (the frame's worker)
[Service]
ExecStart=/usr/bin/python3 %h/.hive/drone.py
Restart=always
[Install]
WantedBy=default.target
UNIT
ln -s ../hive-drone.service "$H/.config/systemd/user/default.target.wants/hive-drone.service"
chown -R bee:bee "$H"
loginctl enable-linger bee || { echo "refused: logind cannot linger here"; exit 4; }
up() { [ "$(curl -s -m 1 -o /dev/null -w '%{http_code}' http://127.0.0.1:4411/)" = 200 ]; }
i=0; until up || [ $i -ge 40 ]; do i=$((i+1)); sleep 0.5; done
up || { echo "refused: the drone did not come up"; exit 4; }
sleep 7          # seen up by the health watch (it reads every 3 s) before it goes dark
# the fault: the account stops lingering, and its user manager goes down
loginctl disable-linger bee
systemctl stop "user@$U.service"
echo "seeded: bee lingers: $(loginctl show-user bee -p Linger --value 2>/dev/null || echo no); drone :4411 http $(curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:4411/)"
