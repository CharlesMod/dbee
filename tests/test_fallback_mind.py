"""When no Hive mind is usable (no seat in time, or the court unreachable), DBee thinks
with its own bundled engine: started on demand on loopback, CPU only, and stopped
when the case ends. A fake engine stands in for llama-server."""
import sys
import textwrap

import pytest

from dbee import config
from dbee.minds import FallbackMind, LocalEngine, Reply

FAKE_ENGINE = textwrap.dedent('''
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1])
    import os
    open(args[args.index("--argv-out") + 1], "w").write(json.dumps(args + ["CUDA=" + os.environ.get("CUDA_VISIBLE_DEVICES", "unset")]))
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            out = json.dumps({"choices": [{"message": {"content": "from the bundled engine"}}],
                              "usage": {"prompt_tokens": 3, "completion_tokens": 4}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", port), H)
    print(f"main: server is listening on http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()
''')


class _NoSeat:
    name = "hive:gemma-4-26b-a4b-iq3s"

    def __init__(self, err):
        self.err, self.calls = err, 0

    def chat(self, *a, **kw):
        self.calls += 1
        raise self.err


class _Seat:
    name = "hive:gemma-4-26b-a4b-iq3s"

    def chat(self, *a, **kw):
        return Reply(text="from the hive", tokens_in=1, tokens_out=1, seconds=0.1, mind=self.name)


@pytest.fixture
def engine(tmp_path):
    script = tmp_path / "fake_engine.py"
    script.write_text(FAKE_ENGINE)
    argv_out = tmp_path / "argv.json"
    e = LocalEngine([sys.executable, str(script)], str(tmp_path / "small.gguf"), label="qwen3.5-4b-iq4xs",
                    extra=["--argv-out", str(argv_out)], log=tmp_path / "mind.log")
    yield e, argv_out
    e.stop()


@pytest.mark.parametrize("err", [RuntimeError("no seat for gemma-4-26b-a4b-iq3s in 120s: no frame serves it"),
                                 ConnectionRefusedError("the court does not answer")])
def test_no_hive_mind_falls_back_to_the_bundled_engine_cpu_only(engine, err):
    e, argv_out = engine
    m = FallbackMind(_NoSeat(err), e, say=lambda s: None)
    r = m.chat([{"role": "user", "content": "x"}], max_tokens=8)
    assert r.text == "from the bundled engine" and r.mind == "local:qwen3.5-4b-iq4xs"
    import json
    argv = json.loads(argv_out.read_text())
    assert argv[argv.index("-ngl") + 1] == "0"                     # never a card the Hive serves from
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert "CUDA=" in argv                                         # and no card visible to it at all
    # the rest of the case stays on the engine: the Hive is not asked again mid-case
    m.chat([{"role": "user", "content": "y"}], max_tokens=8)
    assert m.primary.calls == 1 and m.name == "local:qwen3.5-4b-iq4xs"   # the case records the mind that answered
    m.rest()
    assert not e.running() and m.name == m.primary.name           # stopped when the case ended


def test_a_hive_that_answers_never_starts_the_engine(engine):
    e, _ = engine
    m = FallbackMind(_Seat(), e, say=lambda s: None)
    assert m.chat([{"role": "user", "content": "x"}]).text == "from the hive"
    assert not e.running()


def test_a_refusal_that_is_the_callers_fault_is_not_hidden(engine):
    import urllib.error
    e, _ = engine
    m = FallbackMind(_NoSeat(urllib.error.HTTPError("u", 400, "bad request", {}, None)), e, say=lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        m.chat([{"role": "user", "content": "x"}])
    assert not e.running()


def test_dbee_toml_names_the_fallback(tmp_path):
    p = tmp_path / "dbee.toml"
    p.write_text('[mind]\nspec = "gemma-4-26b-a4b-iq3s"\ncourt = "http://court:4410"\n'
                 '[mind.fallback]\nengine = "/opt/dbee/engine/llama-server"\nmodel = "/opt/dbee/models/q.gguf"\n'
                 'label = "qwen3.5-4b-iq4xs"\nctx = 8192\n')
    c = config.load(p)
    assert c.fallback == {"engine": "/opt/dbee/engine/llama-server", "model": "/opt/dbee/models/q.gguf",
                          "label": "qwen3.5-4b-iq4xs", "ctx": 8192}


def test_the_service_and_the_installers_check_build_the_same_mind(tmp_path):
    from dbee.minds import HiveMind, from_config
    p = tmp_path / "dbee.toml"
    p.write_text('[mind]\nspec = "gemma-4-26b-a4b-iq3s"\ncourt = "http://court:4410"\n'
                 '[mind.fallback]\nengine = "/e/llama-server"\nmodel = "/m/q.gguf"\nlabel = "q"\n'
                 f'[doctor]\nhome = "{tmp_path / "home"}"\n')
    m = from_config(config.load(p))
    assert isinstance(m, FallbackMind) and isinstance(m.primary, HiveMind) and m.local.label == "q"
    assert m.primary.court == "http://court:4410"
