"""dbee.watch — how the doctor sleeps, and what wakes it.

Event-driven where the machine gives an event, a watchdog only where it does
not:

* ``UnitWatcher`` follows ``journalctl -f -o json`` and wakes on a unit
  entering the failed state, a start failing, or an OOM kill: the kernel's and
  systemd's own words, as they land.
* ``HealthWatcher`` is a watchdog on a URL that should answer: an honest timer,
  because an HTTP page offers no event. It wakes on the first miss after a hit.
* ``LineWatcher`` wakes on a journal line matching a pattern (``Input/output
  error``, ``No space left``), once per distinct line per quiet window.

Each watcher yields ``Wake`` events; the doctor debounces them into one case.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from queue import Queue


@dataclass
class Wake:
    kind: str                     # unit_failed | oom | health_miss | line
    what: str                     # the unit, the url, the line
    at: float = field(default_factory=time.time)
    evidence: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.what}"


FAILED = re.compile(r"(?:Failed to start|entered failed state|Failed with result|Main process exited, code=(?:exited|killed), status=[1-9])")
UNIT = re.compile(r"\b([\w@.-]+\.service)\b")
OOM = re.compile(r"(?:Out of memory: Killed process|oom-kill:|OOM killed)")


class UnitWatcher(threading.Thread):
    def __init__(self, patient, q: Queue, *, since: str = "now"):
        super().__init__(daemon=True)
        self.patient, self.q, self.since = patient, q, since
        self.stop = threading.Event()
        self.proc = None

    def run(self):
        self.proc = self.patient.stream(f"journalctl -f -o json --no-pager --since={self.since} -n 0 2>/dev/null")
        for line in self.proc.stdout:
            if self.stop.is_set():
                break
            try:
                e = json.loads(line)
            except ValueError:
                continue
            msg = e.get("MESSAGE") or ""
            if isinstance(msg, list):
                msg = bytes(msg).decode(errors="replace")
            unit = e.get("UNIT") or e.get("_SYSTEMD_UNIT") or ""
            if OOM.search(msg):
                self.q.put(Wake("oom", UNIT.search(msg).group(1) if UNIT.search(msg) else unit or "kernel", evidence=msg))
            elif FAILED.search(msg):
                m = UNIT.search(msg) or UNIT.search(unit)
                self.q.put(Wake("unit_failed", m.group(1) if m else unit or "?", evidence=msg))
        try:
            self.proc.terminate()
        except Exception:
            pass

    def end(self):
        self.stop.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


class LineWatcher(threading.Thread):
    def __init__(self, patient, q: Queue, pattern: str, *, quiet_s: float = 60):
        super().__init__(daemon=True)
        self.patient, self.q, self.pat, self.quiet = patient, q, re.compile(pattern), quiet_s
        self.seen: dict[str, float] = {}
        self.stop = threading.Event()
        self.proc = None

    def run(self):
        self.proc = self.patient.stream("journalctl -f -o cat --no-pager -n 0 2>/dev/null")
        for line in self.proc.stdout:
            if self.stop.is_set():
                break
            if self.pat.search(line):
                k = line.strip()[:120]
                now = time.time()
                if now - self.seen.get(k, 0) > self.quiet:
                    self.seen[k] = now
                    self.q.put(Wake("line", k, evidence=line.strip()))

    def end(self):
        self.stop.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


class HealthWatcher(threading.Thread):
    """The honest timer: a URL polled every ``every_s``; wakes on a miss after a hit."""

    def __init__(self, patient, q: Queue, url: str, *, every_s: float = 5):
        super().__init__(daemon=True)
        self.patient, self.q, self.url, self.every = patient, q, url, every_s
        self.stop = threading.Event()
        self.was_up = None

    def run(self):
        while not self.stop.wait(self.every):
            r = self.patient.run(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 3 {self.url}", timeout=10)
            up = r.out.strip().startswith("2")
            if self.was_up and not up:
                self.q.put(Wake("health_miss", self.url, evidence=f"http {r.out.strip() or 'no answer'}"))
            self.was_up = up

    def end(self):
        self.stop.set()


class EventWatcher(threading.Thread):
    """The platform's own event stream (journald, macOS's unified log, the Windows
    event log subscription), parsed by the platform into wakes. One watcher for any
    machine; `service` narrows it to one service and its critical lines."""

    def __init__(self, patient, q: Queue, service: str = "", pattern: str = ""):
        super().__init__(daemon=True)
        self.patient, self.q, self.service = patient, q, service
        self.plat = patient.platform
        if pattern:
            import copy
            self.plat = copy.copy(self.plat)
            self.plat.critical = pattern
        self.stop = threading.Event()
        self.proc = None

    def run(self):
        cmd = self.plat.watch_cmd(self.service)
        if not cmd:
            return
        self.proc = self.patient.stream(cmd)
        for line in self.proc.stdout:
            if self.stop.is_set():
                break
            ev = self.plat.parse_event(line, self.service)
            if ev:
                self.q.put(Wake(ev["kind"], ev["what"], evidence=ev.get("evidence", "")))

    def end(self):
        self.stop.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
