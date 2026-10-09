"""dbee.notify — a hand-off reaches a person.

A case DBee cannot finish is only useful if someone hears of it. `dbee.toml`:

    [notify]
    url = "https://ntfy.sh/my-dbee-topic"     # a POST of the report, a Title header (ntfy, Gotify-style hooks)
    command = ["/usr/local/bin/tell-me"]      # run with the report on stdin (mail, Telegram, a desktop toast)
    on = ["handed"]                           # which ends are said; "closed" too for every cure

A notice that cannot be sent is said in DBee's log, never raised: the case is
already on disk, and the doctor goes back to sleep either way.
"""
from __future__ import annotations

import subprocess
import urllib.request

SEND_S = 15.0          # a network timeout: the push service is someone else's


def notify(cfg, case) -> list[str]:
    """Send the case's report where the config says, when its end is one to say.
    Returns what failed, in words (empty when all went or none was due)."""
    if not (cfg.notify_url or cfg.notify_cmd) or case.end not in (cfg.notify_on or ["handed"]):
        return []
    w = case.wake or {}
    title = f"DBee {case.end}: {w.get('what', '?')} on {case.patient}"
    body = case.report()
    failed = []
    if cfg.notify_url:
        req = urllib.request.Request(cfg.notify_url, data=body.encode(), method="POST",
                                     headers={"Title": title.encode("ascii", "replace").decode(), "Tags": "dbee",
                                              "Content-Type": "text/markdown; charset=utf-8"})
        try:
            urllib.request.urlopen(req, timeout=SEND_S).close()
        except Exception as e:  # noqa: BLE001 — any failure is said, the case stands
            failed.append(f"notify {cfg.notify_url}: {e}")
    if cfg.notify_cmd:
        try:
            r = subprocess.run(cfg.notify_cmd, input=body, text=True, capture_output=True, timeout=SEND_S * 4)
            if r.returncode != 0:
                failed.append(f"notify {cfg.notify_cmd[0]}: exit {r.returncode}: {r.stderr.strip()[:200]}")
        except Exception as e:  # noqa: BLE001
            failed.append(f"notify {cfg.notify_cmd[0]}: {e}")
    return failed
