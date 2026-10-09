"""The Hive's spine wakes DBee: a frame lost, an organ refusing in a loop, a pin refused,
a job quarantined, and the court gone dark. A fake court at its HTTP boundary."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue, Empty
from urllib.parse import parse_qs, urlparse

from dbee.watch import SpineRules, SpineWatcher


def ev(name, **kw):
    return {"event": name, "ts": time.time(), **kw}


def test_the_rules_wake_on_what_the_hive_doctor_wakes_on():
    r = SpineRules()
    assert r.feed(ev("node_dropped", node="cube"))[0].key == "node_lost:cube"
    out = r.feed(ev("node_dropped", node="queen", cause="court_outage"))
    assert out[0].kind == "court_outage"
    assert r.feed(ev("pin_refused", node="pop-os", model="m", reason="no room"))[0].key == "pin_refused:pop-os"
    assert r.feed(ev("poison", node="cube", job_id="J1", outcome="quarantined"))[0].key == "quarantined:cube"
    assert r.feed(ev("job_state", node="cube")) == [] and r.feed(ev("route_demand")) == []


def test_an_organ_wakes_only_when_it_refuses_three_times_running():
    r = SpineRules()
    refuse = lambda: r.feed(ev("organ_refused", node="d", organ="speech.station", reason="no device"))
    assert refuse() == [] and refuse() == []
    assert r.feed(ev("organ_served", node="d", organ="speech.station")) == []      # served between: the run starts again
    assert refuse() == [] and refuse() == []
    w = refuse()
    assert [x.key for x in w] == ["organ_refused:d/speech.station"] and "no device" in w[0].evidence


class _Court(BaseHTTPRequestHandler):
    batches: list = []
    asked: list = []

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        _Court.asked.append(q)
        if "tail" in q:
            body = {"events": [ev("node_dropped", node="old", seq=7)], "cursor": 7, "tail": 1}
        else:
            got = _Court.batches.pop(0) if _Court.batches else []
            since = int(q["since"][0])
            body = {"events": got, "cursor": max([e["seq"] for e in got] + [since])}
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_the_watcher_starts_at_the_tail_and_follows_the_cursor():
    _Court.asked = []
    _Court.batches = [[ev("node_dropped", node="cube", seq=8)], [ev("pin_refused", node="pop", seq=9)]]
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Court)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    q = Queue()
    w = SpineWatcher(f"http://127.0.0.1:{srv.server_port}", q, wait_s=0.2)
    w.start()
    try:
        got = [q.get(timeout=5).key, q.get(timeout=5).key]
    finally:
        w.end(); srv.shutdown()
    assert got == ["node_lost:cube", "pin_refused:pop"]          # history before the start is not news
    follows = [a for a in _Court.asked if "since" in a]
    assert follows[0]["since"] == ["7"] and follows[1]["since"] == ["8"] and "wait" in follows[0]


def test_a_court_that_stops_answering_wakes_once_and_once_more_only_after_it_answered():
    q = Queue()
    w = SpineWatcher("http://127.0.0.1:9", q, wait_s=0.1, dark_s=0.3, backoff_s=0.05)   # nothing listens on :9
    w.start()
    try:
        first = q.get(timeout=5)
        try:
            again = q.get(timeout=0.8)
        except Empty:
            again = None
    finally:
        w.end()
    assert first.kind == "court_silent" and again is None
