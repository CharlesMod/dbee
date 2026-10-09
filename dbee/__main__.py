"""dbee — the doctor bee.

  dbee watch  [--patient local|podman:NAME|ssh:HOST] --mind MIND [--court URL]   sleep on a machine; treat what wakes you
  dbee treat  --wake unit_failed:nginx.service [--patient ...] --mind MIND          one case, by hand
  dbee sim    [SCENARIO|t1|all] --mind MIND [--court URL] [--keep]                 break a patient, score the doctor
  dbee check  "CMD"                                                                 would this look / cure be allowed?
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from queue import Queue

from . import looks, cures
from .doctor import Doctor, wake_from
from .cures import Runbook
from .minds import mind as make_mind
from .patient import Local, Podman, Ssh

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("DBEE_HOME") or Path.home() / ".dbee")


def patient_of(spec: str):
    if spec == "local":
        return Local()
    kind, _, name = spec.partition(":")
    if kind == "podman":
        return Podman(name)
    if kind == "ssh":
        return Ssh(name)
    raise SystemExit(f"patient? {spec}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dbee", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mind", default=os.environ.get("DBEE_MIND", "gemma-4-26b-a4b"), help="claude[:model] or a hive model name")
    ap.add_argument("--court", default=os.environ.get("DBEE_COURT", ""), help="the hive court's URL for hive minds")
    sub = ap.add_subparsers(dest="verb", required=True)
    w = sub.add_parser("watch"); w.add_argument("--patient", default="local"); w.add_argument("--health", default="", help="a URL that should answer")
    t = sub.add_parser("treat"); t.add_argument("--patient", default="local"); t.add_argument("--wake", required=True, help="kind:what, e.g. unit_failed:nginx.service"); t.add_argument("--evidence", default="")
    s = sub.add_parser("sim"); s.add_argument("pick", nargs="?", default="all"); s.add_argument("--keep", action="store_true"); s.add_argument("--runs", default=str(ROOT / "runs"))
    c = sub.add_parser("check"); c.add_argument("cmd")
    a = ap.parse_args(argv)

    if a.verb == "check":
        print("look:", looks.check(a.cmd) or "allowed")
        print("cure:", cures.check_cure(a.cmd) or "allowed")
        return 0

    m = make_mind(a.mind, court=a.court)
    runbook = Runbook.load(ROOT / "assets" / "runbook.jsonl")

    if a.verb == "sim":
        from . import sim
        picked = sim.scenarios(ROOT / "scenarios", None if a.pick == "all" else a.pick)
        if not picked:
            print("no scenario matches", a.pick); return 2
        results = [sim.run(sc, m, runs_dir=Path(a.runs), keep=a.keep) for sc in picked]
        fixed = sum(1 for r in results if r.get("score", {}).get("fixed"))
        unsafe = sum(len(r.get("score", {}).get("unsafe", [])) for r in results)
        print(f"\n{fixed}/{len(results)} fixed, {unsafe} unsafe acts, mind {m.name}")
        return 0 if fixed == len(results) and not unsafe else 1

    p = patient_of(a.patient)
    doc = Doctor(p, m, home=HOME, runbook=runbook)
    if a.verb == "treat":
        kind, _, what = a.wake.partition(":")
        case = doc.treat(wake_from(kind, what, a.evidence))
        print(f"{case.end}: {case.finding}")
        return 0 if case.end in ("closed", "handed") else 1

    # watch: sleep until something wakes
    from .watch import UnitWatcher, HealthWatcher
    q: Queue = Queue()
    ws = [UnitWatcher(p, q)]
    if a.health:
        ws.append(HealthWatcher(p, q, a.health))
    for x in ws:
        x.start()
    print(f"dbee sleeps on {p.name} ({len(ws)} watchers); mind {m.name}")
    open_cases: dict[str, float] = {}
    try:
        while True:
            wk = q.get()
            if time.time() - open_cases.get(wk.key, 0) < 300:
                continue                                   # the same wake inside five minutes is the same case
            open_cases[wk.key] = time.time()
            case = doc.treat(wk)
            print(f"[{case.id}] {case.end}: {case.finding[:300]}")
            print("dbee sleeps again")
    except KeyboardInterrupt:
        for x in ws:
            x.end()
    return 0


if __name__ == "__main__":
    sys.exit(main())
