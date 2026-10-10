"""A hand-off reaches a person: a POST to a push URL (ntfy and the like), or a command of theirs."""
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from dbee import config
from waspdoctor.doctor import Case
from dbee.notify import notify


class _Push(BaseHTTPRequestHandler):
    got: list = []

    def do_POST(self):
        _Push.got.append((self.path, dict(self.headers), self.rfile.read(int(self.headers["Content-Length"])).decode()))
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


def _handed():
    c = Case(id="c-9", patient="local", wake={"kind": "unit_failed", "what": "pg.service", "evidence": "FATAL: disk"})
    c.end, c.hand = "handed", {"step": "replace the failing disk", "finding": "SMART says the disk is dying"}
    return c


def test_a_hand_off_is_pushed_and_given_to_the_persons_command(tmp_path):
    _Push.got = []
    srv = HTTPServer(("127.0.0.1", 0), _Push)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = tmp_path / "got.md"
    p = tmp_path / "dbee.toml"
    p.write_text(f'[notify]\nurl = "http://127.0.0.1:{srv.server_port}/dbee-alerts"\n'
                 f'command = ["{sys.executable}", "-c", "import sys; open(r\'{out}\', \'w\').write(sys.stdin.read())"]\n')
    cfg = config.load(p)
    try:
        said = notify(cfg, _handed())
    finally:
        srv.shutdown()
    path, headers, body = _Push.got[0]
    assert path == "/dbee-alerts" and "pg.service" in headers["Title"] and "replace the failing disk" in body
    assert "replace the failing disk" in out.read_text()
    assert said == []                                           # nothing failed


def test_a_closed_case_stays_quiet_and_a_dead_push_is_said_not_raised(tmp_path):
    p = tmp_path / "dbee.toml"
    p.write_text('[notify]\nurl = "http://127.0.0.1:9/nowhere"\n')
    cfg = config.load(p)
    c = _handed()
    c.end = "closed"
    assert notify(cfg, c) == []
    c.end = "handed"
    said = notify(cfg, c)
    assert len(said) == 1 and "127.0.0.1:9" in said[0]
