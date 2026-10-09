"""dbee.config — one file says how DBee runs on a machine (`dbee.toml`).

The installer writes it; `dbee watch --config dbee.toml` reads it; a person can
edit it. Every field has a default, so an empty file is a valid one (watch the
whole machine with the mind named by --mind).

    [mind]
    spec = "openai:http://127.0.0.1:8099/v1#qwen3.5-4b-iq4xs"   # or claude:…, a hive model, a URL
    court = "http://queen:4410"   # a hive model's court (its router); DBEE_COURT otherwise
    max_tokens = 1024
    effort = { triage = "low", diagnose = "medium", treat = "medium" }   # thinking models only

    [[watch]]                     # one table per service; none means the whole machine
    service = "nginx"             # a systemd unit, a launchd label, a Windows service
    pattern = "emerg|crit"        # optional: what a critical line looks like (the platform's default otherwise)

    [[watch]]
    health = "http://127.0.0.1:8080/"   # optional: a URL that must answer

    [notify]                      # a case handed to a person reaches them (dbee/notify.py)
    url = "https://ntfy.sh/my-dbee-topic"
    command = ["/usr/local/bin/tell-me"]   # the report on stdin

    [doctor]
    home = "~/.dbee"              # cases, casebook, transcripts
    case_hours = 3                # a case works until this wall-clock bound, then is handed to a person
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Watch:
    service: str = ""
    pattern: str = ""
    health: str = ""


@dataclass
class Config:
    mind: str = ""
    court: str = ""
    max_tokens: int = 0
    effort: dict = field(default_factory=dict)
    watches: list[Watch] = field(default_factory=list)
    home: Path = Path.home() / ".dbee"
    case_hours: float = 0.0
    notify_url: str = ""
    notify_cmd: list[str] = field(default_factory=list)
    notify_on: list[str] = field(default_factory=list)
    path: Path | None = None


def load(path: str | os.PathLike) -> Config:
    p = Path(path).expanduser()
    d = tomllib.loads(p.read_text())
    m = d.get("mind") or {}
    eff = m.get("effort") or {}
    if not isinstance(eff, dict):
        raise ValueError(f"{p}: [mind] effort is a table like {{ triage = \"low\" }}")
    watches = []
    for i, w in enumerate(d.get("watch") or []):
        if not isinstance(w, dict) or not (w.get("service") or w.get("health")):
            raise ValueError(f"{p}: [[watch]] #{i + 1} names neither a service nor a health URL")
        watches.append(Watch(service=str(w.get("service", "")), pattern=str(w.get("pattern", "")),
                             health=str(w.get("health", ""))))
    doc = d.get("doctor") or {}
    n = d.get("notify") or {}
    cmd = n.get("command") or []
    if isinstance(cmd, str) or not all(isinstance(x, str) for x in cmd):
        raise ValueError(f"{p}: [notify] command is a list, like [\"/usr/local/bin/tell-me\", \"--urgent\"]")
    return Config(mind=str(m.get("spec", "")), court=str(m.get("court", "")), max_tokens=int(m.get("max_tokens", 0) or 0),
                  effort={str(k): str(v) for k, v in eff.items()}, watches=watches,
                  home=Path(str(doc.get("home", "~/.dbee"))).expanduser(),
                  case_hours=float(doc.get("case_hours", 0) or 0), notify_url=str(n.get("url", "")),
                  notify_cmd=list(cmd), notify_on=[str(x) for x in n.get("on") or []], path=p)


def apply_env(cfg: Config) -> None:
    """The doctor reads its budgets from the environment; a config sets them once."""
    if cfg.max_tokens:
        os.environ["DBEE_MAX_TOKENS"] = str(cfg.max_tokens)
    if cfg.case_hours:
        os.environ["DBEE_CASE_HOURS"] = str(cfg.case_hours)
    if cfg.effort:
        os.environ["DBEE_EFFORT"] = ",".join(f"{k}={v}" for k, v in cfg.effort.items())
