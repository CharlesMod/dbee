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


def _get(url: str, timeout: float = 30) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


class HiveMind:
    """A seat on the hive, by model name, for one call at a time."""

    def __init__(self, court: str, model: str, *, cls: str = "background", wait_s: float = 120):
        self.court = court.rstrip("/")
        self.model = model
        self.cls = cls
        self.wait_s = wait_s
        self.name = f"hive:{model}"

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
            time.sleep(min(5.0, float(body.get("retry_after_s") or body.get("retry_s") or 2)))
        raise RuntimeError(f"no seat for {self.model} in {self.wait_s:.0f}s: {last.get('detail') or last.get('why') or last}")

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             *, max_tokens: int = 1024, temperature: float = 0.0) -> Reply:
        """One call; an engine that drops mid-call (a restart, a reload) is
        backed off from and asked for again through the router, until wait_s."""
        deadline = time.time() + self.wait_s
        delay = 2.0
        while True:
            try:
                return self._chat_once(messages, tools, max_tokens=max_tokens, temperature=temperature)
            except (urllib.error.URLError, ConnectionError, TimeoutError, http.client.HTTPException) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                    raise
                if time.time() + delay > deadline:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 30.0)

    def _chat_once(self, messages, tools, *, max_tokens, temperature) -> Reply:
        est = sum(len(json.dumps(m)) for m in messages) // 3 + max_tokens
        grant = self._grant(est)
        url = grant["url"].rstrip("/")
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                "temperature": temperature}
        if tools:
            body["tools"] = tools
        t0 = time.time()
        usage, out = {}, {}
        try:
            out = _post(f"{url}/v1/chat/completions", body)
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
        msg = (out.get("choices") or [{}])[0].get("message") or {}
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {"_raw": fn.get("arguments")}
            calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": args})
        return Reply(text=msg.get("content") or "", tool_calls=calls,
                     tokens_in=int(usage.get("prompt_tokens") or 0),
                     tokens_out=int(usage.get("completion_tokens") or 0),
                     seconds=time.time() - t0, mind=self.name, raw=out)


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
             *, max_tokens: int = 1024, temperature: float = 0.0) -> Reply:
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


def mind(spec: str, *, court: str = "", seat: str = "background", wait_s: float = 120) -> HiveMind | ClaudeMind:
    """``claude[:model]`` or a hive model name (``gemma-4-26b-a4b``); ``seat`` is
    the router's call class (a frame keeps some seats for some classes: a 4 GB
    frame's one slot may answer only ``batch``)."""
    if spec.startswith("claude"):
        _, _, model = spec.partition(":")
        return ClaudeMind(model or "claude-sonnet-5-5")
    if not court:
        raise RuntimeError("a hive mind needs the court's address (--court or DBEE_COURT)")
    return HiveMind(court, spec, cls=seat, wait_s=wait_s)
