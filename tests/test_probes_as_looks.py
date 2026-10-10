"""The Hive's probes are the doctor's own first looks for a wake about the drone."""
import base64

from waspdoctor import platform as P
from waspdoctor.doctor import Doctor

from dbee import PROBES
from dbee.patient import Result
from dbee.watch import Wake


class _Patient:
    name = "fake"
    shell = "sh"
    platform = P.LINUX
    runs_as_drone = True

    def __init__(self):
        self.ran = []

    def run(self, cmd, *, timeout=60, user="root", input=None):
        self.ran.append(cmd)
        if cmd.startswith("echo ") and "base64 -d | sh" in cmd:
            script = base64.b64decode(cmd.split()[1]).decode()
            if "downtime probe" in script:
                return Result(1, "RED: the drone runs as bee's own unit and bee does not linger")
        return Result(0, "")


def test_a_wake_about_the_drone_reads_its_probes_first(tmp_path):
    pt = _Patient()
    first = Doctor(pt, mind=None, home=tmp_path, probes=PROBES)._first_look(Wake("health_miss", "http://127.0.0.1:4411/health"))
    assert "$ probe downtime\n[exit 1]\nRED: the drone runs as bee's own unit" in first
    assert "$ probe engine" in first and "$ probe mic" not in first


def test_a_wake_about_anything_else_runs_no_probe(tmp_path):
    pt = _Patient()
    first = Doctor(pt, mind=None, home=tmp_path, probes=PROBES)._first_look(Wake("unit_failed", "cron.service"))
    assert "$ probe" not in first and not any("base64 -d" in c for c in pt.ran)


def test_a_patient_the_drone_does_not_run_gets_no_probe(tmp_path):
    # a probe reads its own context: run by root beside the drone it would say "the drone runs as root"
    pt = _Patient()
    pt.runs_as_drone = False
    first = Doctor(pt, mind=None, home=tmp_path, probes=PROBES)._first_look(Wake("health_miss", "http://127.0.0.1:4411/health"))
    assert "$ probe" not in first


class _Script:
    def __init__(self, *steps):
        self.steps, self.n, self.seen = list(steps), 0, []

    def chat(self, msgs, tools=None, max_tokens=0, effort=""):
        from dbee.minds import Reply
        self.seen.append(msgs[-1].get("content", ""))
        name, args = self.steps[min(self.n, len(self.steps) - 1)]
        self.n += 1
        return Reply(text="", tool_calls=[{"id": f"t{self.n}", "name": name, "arguments": args}])


def test_a_red_probe_offers_its_runbook_fix_and_the_fixes_own_words_run(tmp_path):
    from pathlib import Path
    from waspdoctor.cures import Runbook
    rb = Runbook.load(Path(__file__).resolve().parents[1] / "assets" / "runbook.jsonl")
    pt = _Patient()
    mind = _Script(("diagnose", {"cause": "bee does not linger", "evidence": "RED: the drone runs as bee's own unit and bee does not linger"}),
                   ("cure", {"command": "runbook:linger", "undo": "", "verify": "loginctl show-user bee -p Linger", "why": "linger"}),
                   ("hand", {"step": "x", "finding": "x"}))
    case = Doctor(pt, mind, home=tmp_path, runbook=rb, probes=PROBES).treat(Wake("health_miss", "http://127.0.0.1:4411/health"), case_id="c-rb")
    assert "downtime=1" in case.sig
    assert "`runbook:linger`" in mind.seen[1]                              # the brief offers it by name
    ran = case.cures[0]["cure"]
    assert ran["name"] == "linger" and ran["source"] == "runbook"
    script = base64.b64decode(ran["command"].split()[1]).decode()
    assert "enable-linger" in script and "disable-linger" in base64.b64decode(ran["undo"].split()[1]).decode()


def test_a_runbook_fix_the_signature_did_not_offer_is_refused(tmp_path):
    from pathlib import Path
    from waspdoctor.cures import Runbook
    rb = Runbook.load(Path(__file__).resolve().parents[1] / "assets" / "runbook.jsonl")
    pt = _Patient()
    mind = _Script(("diagnose", {"cause": "x", "evidence": "RED: the drone runs as bee's own unit and bee does not linger"}),
                   ("cure", {"command": "runbook:audio-server", "undo": "", "verify": "uptime", "why": "x"}),
                   ("hand", {"step": "x", "finding": "x"}))
    case = Doctor(pt, mind, home=tmp_path, runbook=rb, probes=PROBES).treat(Wake("health_miss", "http://127.0.0.1:4411/health"), case_id="c-rb2")
    assert not case.cures and "not a runbook fix this case's signature offers" in case.refusals[-1]["why"]
