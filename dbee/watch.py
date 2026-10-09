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
import shlex
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


def subject(wk: Wake) -> str:
    """What a wake is about: the service (a line naming one is about it), else the url or the line."""
    what = wk.what
    if wk.kind == "line":
        m = UNIT.search(wk.evidence or wk.what)
        what = m.group(1) if m else what
    return what[:-len(".service")] if what.endswith(".service") else what


class Fold:
    """One case per fault. A wake raised before the last case on its subject ended
    (the storm a failing service sends while it is treated, the restarts its cure
    causes) belongs to that case; one raised after it ended is the fault coming back
    and opens a case. Keyed on the case's end, an event, never on a quiet window."""

    def __init__(self):
        self._ended: dict[str, float] = {}

    def admit(self, wk: Wake) -> bool:
        return wk.at > self._ended.get(subject(wk), float("-inf"))

    def ended(self, wk: Wake, at: float) -> None:
        self._ended[subject(wk)] = at


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


class FileWatcher(threading.Thread):
    """A plain log file, followed by its name (across a rotation): a line matching
    the pattern (the platform's critical default) wakes DBee. It starts at the
    file's end as it was when DBee began, so old lines never wake it and none
    written while the follower opens is missed."""

    def __init__(self, patient, q: Queue, path: str, pattern: str = ""):
        super().__init__(daemon=True)
        self.patient, self.q, self.path = patient, q, path
        self.pat = re.compile(pattern or patient.platform.critical or r"(?i)\b(error|fatal|panic|crit)")
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.proc = None

    def follow_cmd(self) -> str:
        if self.patient.platform.shell == "powershell":
            p = self.path.replace("'", "''")
            # Get-Content -Wait keeps the file it opened: a rename-rotation on Windows is not followed yet
            return f"'dbee-ready'; Get-Content -LiteralPath '{p}' -Wait -Tail 0"
        q = shlex.quote(self.path)
        return f"n=$(wc -c < {q} 2>/dev/null || echo 0); echo dbee-ready; exec tail -F -c +$((n + 1)) {q} 2>/dev/null"

    def run(self):
        self.proc = self.patient.stream(self.follow_cmd())
        for line in self.proc.stdout:
            if self.stop.is_set():
                break
            if not self.ready.is_set() and line.strip() == "dbee-ready":
                self.ready.set()
                continue
            if self.pat.search(line):
                self.q.put(Wake("line", self.path, evidence=line.strip()))
        self.ready.set()

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
        self.ready = threading.Event()          # subscribed: a fault from now on is seen
        self.proc = None

    def run(self):
        cmd = self.plat.watch_cmd(self.service)
        if not cmd:
            self.ready.set()
            return
        self.proc = self.patient.stream(cmd)
        if not self.plat.says_ready:
            self.ready.set()
        tail: list[str] = []
        try:
            for line in self.proc.stdout:
                if self.stop.is_set():
                    break
                if not self.ready.is_set() and line.strip() == '{"ready":true}':
                    self.ready.set()
                    continue
                ev = self.plat.parse_event(line, self.service)
                if ev:
                    self.q.put(Wake(ev["kind"], ev["what"], evidence=ev.get("evidence", "")))
                elif line.strip():
                    tail = (tail + [line.strip()])[-5:]
        finally:
            self.ready.set()
        if not self.stop.is_set():
            # DBee is blind to this service from here; say so with what the stream said last
            print(f"the watch on {self.service or 'the whole machine'} ended: " + " | ".join(tail)[-600:], flush=True)

    def end(self):
        self.stop.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
