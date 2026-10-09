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
    if kind == "ssh-win":
        return Ssh(name, shell="powershell")
    if kind in ("hive", "hive-win"):
        from .patient import Hive
        return Hive(name, shell="powershell" if kind == "hive-win" else "sh", hive=os.environ.get("DBEE_HIVE", ""))
    raise SystemExit(f"patient? {spec}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dbee", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mind", default=os.environ.get("DBEE_MIND", "gemma-4-26b-a4b-iq3s"), help="claude[:model] or a hive model name")
    ap.add_argument("--court", default=os.environ.get("DBEE_COURT", ""), help="the hive court's URL for hive minds")
    ap.add_argument("--seat", default=os.environ.get("DBEE_SEAT", "background"), help="the router's call class: background, batch, tool, conversation")
    ap.add_argument("--wait", type=float, default=float(os.environ.get("DBEE_WAIT", "120")), help="seconds to wait for a seat before a call fails")
    sub = ap.add_subparsers(dest="verb", required=True)
    w = sub.add_parser("watch"); w.add_argument("service", nargs="?", default="", help="a systemd unit, a launchd label or a Windows service; empty watches the whole machine"); w.add_argument("--patient", default="local", help="local, ssh:HOST, ssh-win:HOST (PowerShell), podman:NAME"); w.add_argument("--health", default="", help="a URL that should answer"); w.add_argument("--pattern", default="", help="what a critical line looks like (a regex); the platform's default otherwise"); w.add_argument("--config", default=os.environ.get("DBEE_CONFIG", ""), help="a dbee.toml: the mind, the services to watch, the doctor's home")
    pl = sub.add_parser("platform"); pl.add_argument("--patient", default="local")
    t = sub.add_parser("treat"); t.add_argument("--patient", default="local"); t.add_argument("--wake", required=True, help="kind:what, e.g. unit_failed:nginx.service"); t.add_argument("--evidence", default="")
    s = sub.add_parser("sim"); s.add_argument("pick", nargs="?", default="all"); s.add_argument("--keep", action="store_true"); s.add_argument("--repeat", type=int, default=1, help="run each scenario N times (a pass rate, not one coin flip)"); s.add_argument("--jobs", type=int, default=int(os.environ.get("DBEE_JOBS", "0")), help="scenarios at once, each its own patient; 0 (the default) runs every picked scenario at once, and calls past the mind's free seats wait at the router"); s.add_argument("--runs", default=str(ROOT / "runs"))
    c = sub.add_parser("check"); c.add_argument("cmd")
    v = sub.add_parser("validate"); v.add_argument("pick", nargs="?", default="all")
    a = ap.parse_args(argv)

    if a.verb == "check":
        print("look:", looks.check(a.cmd) or "allowed")
        print("cure:", cures.check_cure(a.cmd) or "allowed")
        return 0

    if a.verb == "validate":
        from . import sim
        res = [sim.validate(sc) for sc in sim.scenarios(ROOT / "scenarios", None if a.pick == "all" else a.pick)]
        print(f"{sum(r['ok'] for r in res)}/{len(res)} scenarios valid")
        return 0 if all(r["ok"] for r in res) else 1

    if a.verb == "platform":
        p = patient_of(a.patient)
        print(f"{p.name}: {p.platform.name} ({p.platform.shell})")
        return 0

    cfg = None
    if getattr(a, "config", ""):
        from . import config as _config
        cfg = _config.load(a.config)
        _config.apply_env(cfg)
        if cfg.mind:
            a.mind = cfg.mind
        if cfg.court and not a.court:
            a.court = cfg.court
        globals()["HOME"] = cfg.home
    m = make_mind(a.mind, court=a.court, seat=a.seat, wait_s=a.wait)
    runbook = Runbook.load(ROOT / "assets" / "runbook.jsonl")

    if a.verb == "sim":
        from . import sim
        picked = sim.scenarios(ROOT / "scenarios", None if a.pick == "all" else a.pick) * max(1, a.repeat)
        if not picked:
            print("no scenario matches", a.pick); return 2
        jobs = a.jobs if a.jobs > 0 else len(picked)
        if jobs > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                results = list(pool.map(lambda sc: sim.run(sc, m, runs_dir=Path(a.runs), keep=a.keep), picked))
        else:
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
    from .watch import EventWatcher, HealthWatcher, Wake
    q: Queue = Queue()
    plan = [(a.service, a.pattern, a.health)] if (a.service or a.health or not cfg or not cfg.watches) \
        else [(w.service, w.pattern, w.health) for w in cfg.watches]
    ws, named = [], []
    for svc, pattern, health in plan:
        if svc or not health:
            service = p.platform.resolve(p, svc)["service"] if svc else ""
            ws.append(EventWatcher(p, q, service, pattern))
            named.append(service or "the whole machine")
        if health:
            ws.append(HealthWatcher(p, q, health))
            named.append(health)
    service = ", ".join(named)
    for x in ws:
        x.start()
    for x in ws:
        if isinstance(x, EventWatcher):
            x.ready.wait()
            said = x.service and p.platform.down_at_start(p, x.service)
            if said:
                q.put(Wake("unit_failed", x.service, evidence=f"already down as DBee began to watch it: {said}"))
    print(f"dbee sleeps on {p.name} ({p.platform.name}; watching {service}); mind {m.name}")
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
