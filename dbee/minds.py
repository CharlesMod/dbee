"""dbee.minds — where a thought goes.

Two kinds of mind, one call shape (`chat(messages, tools=None) -> reply`):

* `HiveMind` asks the hive's router for a seat (``GET /v1/route``), calls the
  engine's own OpenAI-style endpoint, and gives the seat back
  (``POST /v1/route/done``). DBee is an outside client of the hive here, like
  any program on the tailnet; nothing it does is a hive job.
* `ClaudeMind` calls Anthropic's API: the ceiling each scenario is measured
  against. The key comes from ``ANTHROPIC_API_KEY`` or
  ``~/.config/dbee/secrets.env`` (owner-only), never from the tree.

Every reply carries its usage so the scoreboard can count tokens and seconds.
"""
from __future__ import annotations

import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SECRETS = Path.home() / ".config" / "dbee" / "secrets.env"


@dataclass
class Reply:
    text: str
    tool_calls: list = field(default_factory=list)   # [{"name", "arguments": dict, "id"}]
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    mind: str = ""
    raw: dict | None = None
    reasoning: str = ""                              # a thinking model's reasoning, when the server returns it
    served: dict = field(default_factory=dict)       # where it ran: a hive seat's node, url and slot


def _secret(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in SECRETS.read_text().splitlines():
            k, _, v = line.strip().partition("=")
            if k == name and v:
                return v.strip().strip('"')
    except OSError:
        pass
    return ""


def _post(url: str, body: dict, headers: dict | None = None, timeout: float = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# Silence, not length, ends a call: a slow machine reads a long prompt for
# minutes, and llama-server says how far it is (return_progress) while it does.
SILENCE_S = 120.0


def _post_stream(url: str, body: dict, headers: dict | None = None, silence_s: float | None = None) -> dict:
    """A chat call streamed, assembled into the reply a plain call returns. The
    socket timeout is a watchdog for silence: each progress or token chunk
    resets it. A server that ignores `stream` and answers JSON is read as is."""
    body = {**body, "stream": True, "stream_options": {"include_usage": True}, "return_progress": True}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=silence_s or SILENCE_S) as r:
        if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
            return json.loads(r.read())
        return _assemble(r)


def _assemble(lines) -> dict:
    """OpenAI stream chunks (`data: {...}` lines) into one chat completion."""
    text, think, calls, usage, finish = [], [], {}, {}, None
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            ch = json.loads(data)
        except ValueError:
            continue
        if ch.get("usage"):
            usage = ch["usage"]
        for c in ch.get("choices") or []:
            d = c.get("delta") or {}
            if d.get("content"):
                text.append(d["content"])
            if d.get("reasoning_content"):
                think.append(d["reasoning_content"])
            for tc in d.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", len(calls)), {"id": "", "type": "function",
                                                                       "function": {"name": "", "arguments": ""}})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                slot["function"]["name"] += fn.get("name") or ""
                slot["function"]["arguments"] += fn.get("arguments") or ""
            finish = c.get("finish_reason") or finish
    msg = {"role": "assistant", "content": "".join(text)}
    if think:
        msg["reasoning_content"] = "".join(think)
    if calls:
        msg["tool_calls"] = [calls[k] for k in sorted(calls)]
    return {"choices": [{"message": msg, "finish_reason": finish}], "usage": usage}


def _get(url: str, timeout: float = 30) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def openai_body(model: str, messages, tools, max_tokens: int, temperature: float, effort: str = "") -> dict:
    """A chat call as any OpenAI-compatible server takes it; `n_predict` is
    llama.cpp's own cap (a server's default can otherwise override max_tokens),
    `chat_template_kwargs` its per-request reasoning effort, and the top-level
    `reasoning_effort` is the same for vLLM, Ollama and OpenAI; each ignores the other's."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "n_predict": max_tokens, "temperature": temperature}
    if effort:
        body["chat_template_kwargs"] = {"reasoning_effort": effort}
        body["reasoning_effort"] = effort
    if tools:
        body["tools"] = tools
    return body


def openai_reply(out: dict, seconds: float, name: str) -> "Reply":
    msg = (out.get("choices") or [{}])[0].get("message") or {}
    usage = out.get("usage") or {}
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {"_raw": fn.get("arguments")}
        calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": args})
    return Reply(text=msg.get("content") or "", tool_calls=calls, reasoning=msg.get("reasoning_content") or "",
                 tokens_in=int(usage.get("prompt_tokens") or 0),
                 tokens_out=int(usage.get("completion_tokens") or 0),
                 seconds=seconds, mind=name, raw=out)


class OpenAIMind:
    """Any OpenAI-compatible endpoint: DBee's own ride-along llama-server, Ollama,
    LM Studio, vLLM, a hosted API. `url` is the base (…/v1); the key, when one is
    needed, comes from the environment variable it names or ~/.config/dbee/secrets.env."""

    def __init__(self, url: str, model: str = "", key_env: str = "", wait_s: float = 120):
        self.url = url.rstrip("/")
        if not self.url.endswith("/v1"):
            self.url += "/v1"
        self.model, self.key_env, self.wait_s = model, key_env, wait_s
        self.name = f"openai:{model or self.url}"
        self.say = print

    def chat(self, messages, tools=None, *, max_tokens: int = 1024, temperature: float = 0.0, effort: str = "") -> "Reply":
        """One call; a server that is down or restarting is backed off from until wait_s."""
        headers = {}
        key = _secret(self.key_env) if self.key_env else ""
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = openai_body(self.model or "local", messages, tools, max_tokens, temperature, effort)
        deadline, delay = time.time() + self.wait_s, 2.0
        while True:
            t0 = time.time()
            try:
                out = _post_stream(f"{self.url}/chat/completions", body, headers=headers)
                return openai_reply(out, time.time() - t0, self.name)
            except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code < 500 and e.code != 429:
                    raise
                if time.time() + delay > deadline:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 30.0)


class NoSeat(RuntimeError):
    """The Hive answered, but no seat came for the model within the call's wait: the
    Hive is busy, not broken. A case keeps asking until its own clock runs out."""


class HiveMind:
    """A seat on the hive, by model name, for one call at a time."""

    def __init__(self, court: str, model: str, *, cls: str = "background", wait_s: float = 120):
        self.court = court.rstrip("/")
        self.model = model
        self.cls = cls
        self.wait_s = wait_s
        self.name = f"hive:{model}"
        self.say = print

    def _grant(self, tokens: int) -> dict:
        """Ask until a seat is granted or ``wait_s`` has passed. The court holds a
        refusal only ``hold`` seconds a call (its `wait`), and says when to ask
        again (`retry_after_s`); a seat another caller holds frees at its done."""
        hold = min(10.0, self.wait_s)
        q = urllib.parse.urlencode({"class": self.cls, "model": self.model,
                                    "tokens": tokens, "wait": hold})
        deadline = time.time() + self.wait_s
        last = {}
        while True:
            code, body = _get(f"{self.court}/v1/route?{q}", timeout=hold + 20)
            if code == 200 and body.get("url"):
                return body
            last = body
            if time.time() > deadline:
                break
            if self.say and time.time() - getattr(self, "_said", 0) > 30:
                self._said = time.time()
                self.say(f"   waiting for a seat on {self.model}: {(body.get('detail') or body.get('why') or '')[:120]}")
            time.sleep(min(5.0, float(body.get("retry_after_s") or body.get("retry_s") or 2)))
        raise NoSeat(f"no seat for {self.model} in {self.wait_s:.0f}s: {last.get('detail') or last.get('why') or last}")

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             *, max_tokens: int = 1024, temperature: float = 0.0, effort: str = "") -> Reply:
        """One call; an engine that drops mid-call (a restart, a reload) is
        backed off from and asked for again through the router, until wait_s."""
        deadline = time.time() + self.wait_s
        delay = 2.0
        while True:
            try:
                return self._chat_once(messages, tools, max_tokens=max_tokens, temperature=temperature, effort=effort)
            except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                    raise
                if time.time() + delay > deadline:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 30.0)

    def _chat_once(self, messages, tools, *, max_tokens, temperature, effort="") -> Reply:
        est = sum(len(json.dumps(m)) for m in messages) // 3 + max_tokens
        grant = self._grant(est)
        url = grant["url"].rstrip("/")
        # n_predict beside max_tokens: the engine's own cap, which a pin's default
        # otherwise overrides (seen: 12000 on a call that asked 4096)
        body = openai_body(self.model, messages, tools, max_tokens, temperature, effort)
        if grant.get("slot") is not None:
            # the seat the court granted, not one llama-server picks: an unpinned call
            # lands by LRU on another caller's slot and reads that conversation's state
            body["id_slot"] = int(grant["slot"])
        t0 = time.time()
        usage, out = {}, {}
        try:
            out = _post_stream(f"{url}/v1/chat/completions", body)
        finally:
            usage = out.get("usage") or {}
            try:
                _post(f"{self.court}/v1/route/done",
                      {"node": grant.get("node", ""), "url": grant.get("url", ""),
                       "slot": int(grant.get("slot", 0) or 0),
                       "tokens": int(usage.get("total_tokens") or 0),
                       **({"timings": out["timings"]} if out.get("timings") else {})},
                      timeout=5)
            except Exception:  # noqa: BLE001 — the engine's idle reading frees the seat then
                pass
        r = openai_reply(out, time.time() - t0, self.name)
        r.served = {"node": grant.get("node", ""), "url": grant.get("url", ""), "slot": int(grant.get("slot", 0) or 0)}
        return r


class ClaudeMind:
    """Anthropic's API as the ceiling. Tools are passed in OpenAI shape and
    translated, so the loop sees one shape whichever mind answers."""

    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str = "claude-sonnet-5-5"):
        self.model = model
        self.name = f"claude:{model}"
        self.key = _secret("ANTHROPIC_API_KEY")
        if not self.key:
            raise RuntimeError(f"no ANTHROPIC_API_KEY in the environment or {SECRETS}")

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        out = []
        for t in tools:
            fn = t.get("function") or t
            out.append({"name": fn["name"], "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})
        return out

    @staticmethod
    def _messages(messages: list[dict]) -> tuple[str, list[dict]]:
        system, out = [], []
        for m in messages:
            role, content = m.get("role"), m.get("content")
            if role == "system":
                system.append(content or "")
            elif role == "tool":
                out.append({"role": "user", "content": [{"type": "tool_result",
                                                         "tool_use_id": m.get("tool_call_id", ""),
                                                         "content": content or ""}]})
            elif role == "assistant" and m.get("tool_calls"):
                blocks = [{"type": "text", "text": content}] if content else []
                for tc in m["tool_calls"]:
                    fn = tc.get("function") or tc
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args or "{}")
                        except ValueError:
                            args = {"_raw": args}
                    blocks.append({"type": "tool_use", "id": tc.get("id", ""),
                                   "name": fn.get("name", ""), "input": args or {}})
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": role, "content": content or ""})
        return "\n\n".join(system), out

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             *, max_tokens: int = 1024, temperature: float = 0.0, effort: str = "") -> Reply:
        system, msgs = self._messages(messages)
        body = {"model": self.model, "max_tokens": max_tokens, "messages": msgs,
                "temperature": temperature}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = self._tools(tools)
        t0 = time.time()
        out = _post(self.URL, body, headers={"x-api-key": self.key,
                                             "anthropic-version": "2023-06-01"})
        text, calls = [], []
        for b in out.get("content") or []:
            if b.get("type") == "text":
                text.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                calls.append({"id": b.get("id", ""), "name": b.get("name", ""),
                              "arguments": b.get("input") or {}})
        usage = out.get("usage") or {}
        return Reply(text="".join(text), tool_calls=calls,
                     tokens_in=int(usage.get("input_tokens") or 0),
                     tokens_out=int(usage.get("output_tokens") or 0),
                     seconds=time.time() - t0, mind=self.name, raw=out)


class LocalEngine:
    """DBee's own bundled engine (llama-server), kept for when no Hive mind is usable:
    started on demand on loopback with no layers on any card (``-ngl 0``: a Hive
    frame's cards are the Hive's), ready when it says it is listening, stopped when
    the case ends. ``server`` is the program (or an argv head)."""

    READY_S = 600                     # a cold model read from a slow disk, at most

    def __init__(self, server, model: str, *, label: str = "", ctx: int = 8192, threads: int = 0,
                 extra: list[str] | None = None, log=None):
        self.head = list(server) if isinstance(server, (list, tuple)) else [server]
        self.model, self.ctx, self.threads = model, ctx, threads
        self.label = label or os.path.splitext(os.path.basename(model))[0]
        self.extra, self.log = list(extra or []), log
        self.proc, self.port = None, 0

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.running():
            return
        import socket
        import subprocess
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        argv = [*self.head, "-m", self.model, "--host", "127.0.0.1", "--port", str(self.port),
                "-c", str(self.ctx), "-ngl", "0", "--jinja",
                *(["-t", str(self.threads)] if self.threads else []), *self.extra]
        # no card at all, even for a GPU build named by hand: a Hive frame's cards are the Hive's
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "HIP_VISIBLE_DEVICES": "", "GGML_VK_VISIBLE_DEVICES": ""}
        self.proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     errors="replace", env=env)
        # ready is the engine's own word ("server is listening"), read as it is said;
        # the log keeps every line for a person
        seen: list[str] = []
        ready = threading.Event()

        def pump():
            fh = open(self.log, "a") if self.log else None
            try:
                for line in self.proc.stdout:
                    if fh:
                        fh.write(line); fh.flush()
                    seen.append(line.rstrip()); del seen[:-20]
                    if "listening" in line:
                        ready.set()
            finally:
                ready.set()
                if fh:
                    fh.close()
        threading.Thread(target=pump, daemon=True).start()
        ready.wait(self.READY_S)
        if not self.running() or not any("listening" in x for x in seen):
            self.stop()
            raise RuntimeError("DBee's own engine did not start: " + " | ".join(seen[-5:]))

    def mind(self) -> "OpenAIMind":
        m = OpenAIMind(f"http://127.0.0.1:{self.port}/v1", model=self.label, wait_s=60)
        m.name = f"local:{self.label}"
        return m

    def stop(self) -> None:
        p, self.proc = self.proc, None
        if p is None or p.poll() is not None:
            return                    # never signal a reaped pid
        p.terminate()
        try:
            p.wait(15)
        except Exception:  # noqa: BLE001
            p.kill()
            p.wait(5)


class FallbackMind:
    """The Hive's mind first; DBee's own engine when the Hive cannot answer (no seat
    within the mind's wait, or the court unreachable). Once fallen back, the rest of
    the case stays on the engine; ``rest()`` at the case's end stops it, and the
    next case asks the Hive again. A refusal that is the caller's own fault (an HTTP
    4xx) is raised, never hidden behind the engine."""

    def __init__(self, primary, local: LocalEngine, *, say=print):
        self.primary, self.local, self.say = primary, local, say
        self.name = primary.name
        self.fell_back = False

    def chat(self, messages, tools=None, **kw) -> Reply:
        if not self.fell_back:
            try:
                return self.primary.chat(messages, tools, **kw)
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    raise
                why = e
            except (RuntimeError, OSError, http.client.HTTPException) as e:
                why = e
            self.say(f"   no Hive mind is usable ({str(why)[:160]}); thinking with DBee's own engine, "
                     f"{self.local.label}, on the CPU")
            self.local.start()
            self.fell_back = True
            self.name = f"local:{self.local.label}"
        return self.local.mind().chat(messages, tools, **kw)

    def rest(self) -> None:
        self.fell_back, self.name = False, self.primary.name
        self.local.stop()


def mind(spec: str, *, court: str = "", seat: str = "background", wait_s: float = 120) -> HiveMind | ClaudeMind:
    """``claude[:model]`` or a hive model name (``gemma-4-26b-a4b-iq3s``); ``seat`` is
    the router's call class (a frame keeps some seats for some classes: a 4 GB
    frame's one slot may answer only ``batch``)."""
    if spec.startswith("claude"):
        _, _, model = spec.partition(":")
        return ClaudeMind(model or "claude-sonnet-5-5")
    if spec.startswith("file:"):
        return FileMind(spec[5:])
    if spec.startswith(("openai:", "http://", "https://")):
        # openai:URL[#model][@KEY_ENV]   e.g. openai:http://127.0.0.1:8099/v1#qwen3.5-4b
        rest = spec[len("openai:"):] if spec.startswith("openai:") else spec
        rest, _, key_env = rest.partition("@") if "@" in rest.split("//", 1)[-1] else (rest, "", "")
        url, _, model = rest.partition("#")
        return OpenAIMind(url, model=model, key_env=key_env, wait_s=wait_s)
    court = court or os.environ.get("DBEE_COURT", "")
    if not court:
        raise RuntimeError("a hive mind needs the court's address (--court, DBEE_COURT or [mind] court)")
    return HiveMind(court, spec, cls=seat, wait_s=wait_s)


def from_config(cfg, spec: str = "", *, court: str = "", seat: str = "background", wait_s: float = 120):
    """The mind a dbee.toml describes, the one way `dbee watch` and the installer's
    check both build it: its spec, with DBee's own engine behind it when the
    config names a fallback."""
    m = mind(spec or cfg.mind, court=court or cfg.court, seat=seat, wait_s=wait_s)
    fb = getattr(cfg, "fallback", None)
    if not fb:
        return m
    logs = cfg.home.parent / "logs"
    return FallbackMind(m, LocalEngine(os.path.expanduser(fb["engine"]), os.path.expanduser(fb["model"]),
                                       label=fb.get("label", ""), ctx=int(fb.get("ctx", 8192)),
                                       threads=int(fb.get("threads", 0)),
                                       log=logs / "fallback.log" if logs.is_dir() else None))


class FileMind:
    """A person (or a session) in the doctor's seat: each turn's messages and tools
    are written to ``<dir>/turn-N.json``, and the call waits for ``<dir>/reply-N.json``
    ({"text": "...", "tool_calls": [{"name": ..., "arguments": {...}}]}). The seat
    sees exactly what a mind would, nothing more."""

    def __init__(self, dir: str):
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name = "file:" + self.dir.name
        self.n = 0
        self.say = print

    def chat(self, messages, tools=None, *, max_tokens=1024, temperature=0.0, effort="") -> Reply:
        self.n += 1
        ask = self.dir / f"turn-{self.n}.json"
        ask.write_text(json.dumps({"messages": messages, "tools": [t["function"]["name"] for t in tools or []]}, indent=1))
        rep = self.dir / f"reply-{self.n}.json"
        t0 = time.time()
        while not rep.exists():                       # the seat answers when it answers
            time.sleep(0.5)
        time.sleep(0.2)
        r = json.loads(rep.read_text())
        calls = [{"id": f"me_{self.n}_{i}", "name": c["name"], "arguments": c.get("arguments") or {}}
                 for i, c in enumerate(r.get("tool_calls") or [])]
        return Reply(text=r.get("text", ""), tool_calls=calls, seconds=time.time() - t0, mind=self.name)
