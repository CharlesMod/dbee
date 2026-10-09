"""DBee standalone: a generic OpenAI-compatible mind, and dbee.toml."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from dbee import config
from dbee.minds import OpenAIMind, mind


class _Fake(BaseHTTPRequestHandler):
    seen: list = []
    fail_first = 0

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.seen.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization", "")})
        if _Fake.fail_first > 0:
            _Fake.fail_first -= 1
            self.send_response(503); self.end_headers(); return
        out = {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "look", "arguments": json.dumps({"cmd": "df -h"})}}]}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 9}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    _Fake.seen, _Fake.fail_first = [], 0
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_an_openai_endpoint_answers_with_tool_calls(server, monkeypatch):
    monkeypatch.setenv("DBEE_TEST_KEY", "k-123")
    m = mind(f"openai:{server}/v1#qwen3.5-4b-iq4xs@DBEE_TEST_KEY")
    r = m.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {"name": "look"}}],
               max_tokens=64, effort="low")
    assert r.tool_calls == [{"id": "c1", "name": "look", "arguments": {"cmd": "df -h"}}]
    assert (r.tokens_in, r.tokens_out) == (120, 9)
    sent = _Fake.seen[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["auth"] == "Bearer k-123"
    assert sent["body"]["model"] == "qwen3.5-4b-iq4xs"
    assert sent["body"]["n_predict"] == 64 and sent["body"]["chat_template_kwargs"] == {"reasoning_effort": "low"}


def test_a_restarting_server_is_waited_out(server):
    _Fake.fail_first = 1
    r = OpenAIMind(server, model="m", wait_s=20).chat([{"role": "user", "content": "x"}], max_tokens=8)
    assert r.tool_calls and len(_Fake.seen) == 2


def test_a_bare_url_is_a_mind_and_gets_v1():
    m = mind("http://127.0.0.1:11434#llama3")
    assert isinstance(m, OpenAIMind) and m.url == "http://127.0.0.1:11434/v1" and m.model == "llama3"


def test_dbee_toml(tmp_path):
    p = tmp_path / "dbee.toml"
    p.write_text('[mind]\nspec = "openai:http://127.0.0.1:8099/v1#m"\nmax_tokens = 900\n'
                 'effort = { triage = "low", diagnose = "medium" }\n'
                 '[[watch]]\nservice = "nginx"\n[[watch]]\nservice = "pg"\npattern = "FATAL"\n'
                 '[[watch]]\nhealth = "http://127.0.0.1:8080/"\n[doctor]\nhome = "' + str(tmp_path / "h") + '"\n')
    c = config.load(p)
    assert c.mind.endswith("#m") and c.max_tokens == 900
    assert [(w.service, w.pattern, w.health) for w in c.watches] == [("nginx", "", ""), ("pg", "FATAL", ""), ("", "", "http://127.0.0.1:8080/")]
    assert c.home == tmp_path / "h"
    config.apply_env(c)
    import os
    assert os.environ["DBEE_MAX_TOKENS"] == "900" and os.environ["DBEE_EFFORT"] == "triage=low,diagnose=medium"


def test_an_empty_config_watches_the_whole_machine(tmp_path):
    p = tmp_path / "dbee.toml"
    p.write_text("")
    c = config.load(p)
    assert c.watches == [] and c.mind == ""


def test_a_watch_naming_nothing_is_refused(tmp_path):
    p = tmp_path / "dbee.toml"
    p.write_text('[[watch]]\npattern = "x"\n')
    with pytest.raises(ValueError, match="neither a service nor a health"):
        config.load(p)


def test_a_hive_mind_takes_its_court_from_the_environment(monkeypatch):
    monkeypatch.setenv("DBEE_COURT", "http://court.example:4410")
    m = mind("gemma-4-26b-a4b-iq3s")
    assert m.court == "http://court.example:4410"
    monkeypatch.delenv("DBEE_COURT")
    with pytest.raises(RuntimeError, match="court"):
        mind("gemma-4-26b-a4b-iq3s")


def test_dbee_toml_names_a_hive_court(tmp_path):
    p = tmp_path / "dbee.toml"
    p.write_text('[mind]\nspec = "gemma-4-26b-a4b-iq3s"\ncourt = "http://court.example:4410"\n')
    assert config.load(p).court == "http://court.example:4410"


class _Slow(BaseHTTPRequestHandler):
    """A slow machine: it reads the prompt for longer than the silence bound, saying
    how far it is, then streams a tool call in pieces."""
    def do_POST(self):
        import time
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["stream"] is True
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        def say(d):
            self.wfile.write(b"data: " + json.dumps(d).encode() + b"\n\n"); self.wfile.flush()
        for i in range(6):
            time.sleep(0.2)
            say({"choices": [], "prompt_progress": {"processed": i, "total": 6}})
        say({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "look", "arguments": "{\"cmd\": "}}]}}]})
        say({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\"df -h\"}"}}]}, "finish_reason": "tool_calls"}]})
        say({"choices": [], "usage": {"prompt_tokens": 4607, "completion_tokens": 12}})
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *a):
        pass


def test_a_slow_mind_that_keeps_talking_is_not_timed_out(monkeypatch):
    from dbee import minds
    monkeypatch.setattr(minds, "SILENCE_S", 0.5)   # the whole answer takes > 1 s; no gap reaches 0.5
    srv = HTTPServer(("127.0.0.1", 0), _Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = OpenAIMind(f"http://127.0.0.1:{srv.server_port}/v1", model="m", wait_s=0).chat(
            [{"role": "user", "content": "x"}], max_tokens=8)
    finally:
        srv.shutdown()
    assert r.tool_calls == [{"id": "c1", "name": "look", "arguments": {"cmd": "df -h"}}]
    assert (r.tokens_in, r.tokens_out) == (4607, 12)
