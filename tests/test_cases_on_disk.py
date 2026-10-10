"""A case is on disk after every turn, and exports as training data."""
import io
import json

import pytest

from dbee import platform as P
from dbee.doctor import Doctor, export_cases
from dbee.minds import Reply
from dbee.patient import Result
from dbee.watch import Wake


class _Patient:
    name = "fake"
    shell = "sh"
    platform = P.LINUX

    def run(self, cmd, *, timeout=60, user="root", input=None):
        if "ExecStart" in cmd:
            return Result(0, "{ path=/usr/sbin/cron ; argv[]=/usr/sbin/cron -f ; }")
        if cmd.startswith("ls -lL"):
            return Result(0, "-rw-r--r-- 1 root root 60080 Mar 31  2024 /usr/sbin/cron")
        if cmd.startswith("file -b"):
            return Result(127, "sh: 1: file: not found")     # a slim image has no `file`
        if cmd.startswith("head -c 4"):
            return Result(0, " 177   E   L   F\n")
        return Result(0, "")


class _Stopped(BaseException):          # a stop (SystemExit, KeyboardInterrupt) passes the doctor's catch
    pass


class _Mind:
    name = "fake-4b"

    def __init__(self):
        self.calls = 0

    def chat(self, msgs, tools=None, max_tokens=0, effort=""):
        self.calls += 1
        if self.calls == 1:
            return Reply(text="", tool_calls=[{"id": "c1", "name": "look", "arguments": {"cmd": "uptime"}}],
                         tokens_in=10, tokens_out=3, seconds=0.1, reasoning="check load first")
        raise _Stopped()        # the machine went away mid-case: not an error the doctor catches


def test_a_case_cut_short_is_on_disk_with_what_the_mind_saw_and_exports(tmp_path):
    doc = Doctor(_Patient(), _Mind(), home=tmp_path)
    with pytest.raises(_Stopped):
        doc.treat(Wake("unit_failed", "cron.service", evidence="status=203/EXEC"), case_id="c-1")
    c = json.loads((tmp_path / "cases" / "c-1.json").read_text())
    opening = c["transcript"][1]["content"]
    assert "$ ls -lL /usr/sbin/cron" in opening and "-rw-r--r--" in opening     # the program's mode is in view
    assert "E   L   F" in opening and "head -80" not in opening    # and that it is a binary, with no `file` on the patient
    assert [m["role"] for m in c["transcript"]] == ["system", "user", "assistant", "tool"]
    assert c["turn_log"][0]["tools"] == ["look", "diagnose", "hand"] and c["turn_log"][0]["reasoning"] == "check load first"
    assert c["mind"] == "fake-4b" and c["platform"] == "linux" and not c["closed"]
    out = io.StringIO()
    assert export_cases(tmp_path, out) == 1
    rec = json.loads(out.getvalue())
    assert rec["messages"] == c["transcript"] and rec["turns"][0]["at"] == 2
    assert rec["meta"]["won"] is False and rec["meta"]["complete"] is False
    assert {t["function"]["name"] for t in rec["tools"]} >= {"look", "diagnose", "cure", "hand", "close"}
    assert export_cases(tmp_path, io.StringIO(), won_only=True) == 0


class _Script:
    """A mind that plays a script: each step is a tool call (name, arguments); the
    last step repeats. It keeps the kit each turn was offered."""
    name = "fake"

    def __init__(self, *steps, pause=0.0):
        self.steps, self.n, self.kits, self.pause = list(steps), 0, [], pause

    def chat(self, msgs, tools=None, max_tokens=0, effort=""):
        import time
        time.sleep(self.pause)
        self.kits.append([t["function"]["name"] for t in tools or []])
        name, args = self.steps[min(self.n, len(self.steps) - 1)]
        self.n += 1
        return Reply(text="", tool_calls=[{"id": f"t{self.n}", "name": name, "arguments": args}])


UNREAD = ("diagnose", {"cause": "EXTRA_OPTS is unset", "evidence": "cron: EXTRA_OPTS evaluates to an empty string"})
READ = ("diagnose", {"cause": "cron lost its execute bit", "evidence": "-rw-r--r-- 1 root root 60080 Mar 31  2024 /usr/sbin/cron"})
HAND = ("hand", {"step": "x", "finding": "x"})


def test_no_ungrounded_diagnosis_is_recorded_and_the_case_works_until_its_clock(tmp_path, monkeypatch):
    monkeypatch.setenv("DBEE_CASE_HOURS", str(1.5 / 3600))           # a 1.5 s case
    doc = Doctor(_Patient(), _Script(UNREAD, pause=0.05), home=tmp_path)
    case = doc.treat(Wake("unit_failed", "cron.service", evidence="status=203/EXEC"), case_id="c-2")
    assert case.diagnosis is None and case.end == "handed" and len(case.refusals) > 3   # refused every time, never let through
    assert "ran" in case.hand["step"] and "no diagnosis grounded" in case.finding


def test_a_refused_diagnosis_gives_the_looks_back_and_a_grounded_one_is_recorded(tmp_path):
    from dbee.doctor import LOOK_BUDGET
    looks = [("look", {"cmd": f"uptime{' ' * i}"}) for i in range(LOOK_BUDGET)]
    mind = _Script(*looks, UNREAD, ("look", {"cmd": "ls -lL /usr/sbin/cron"}), READ, HAND)
    case = Doctor(_Patient(), mind, home=tmp_path).treat(Wake("unit_failed", "cron.service"), case_id="c-3")
    assert mind.kits[LOOK_BUDGET] == ["diagnose", "hand"]                  # looks spent: decide
    assert mind.kits[LOOK_BUDGET + 1] == ["look", "hand"]                  # refused: looks given back, diagnose after one
    assert case.diagnosis and case.diagnosis["evidence"].startswith("-rw-r--r--") and case.ungrounded == 1


def test_a_refused_diagnosis_is_not_offered_again_until_a_look_lands(tmp_path):
    # seen live: a 4B on the CPU sent one refused diagnosis 19 times, reading nothing between
    mind = _Script(UNREAD, UNREAD, ("look", {"cmd": "ls -lL /usr/sbin/cron"}), READ, HAND)
    case = Doctor(_Patient(), mind, home=tmp_path).treat(Wake("unit_failed", "cron.service"), case_id="c-4")
    assert mind.kits[1] == ["look", "hand"] and mind.kits[2] == ["look", "hand"]    # no diagnose in the kit
    assert case.ungrounded == 1 and case.refusals[1]["why"] == "no look since the last refusal"
    assert "diagnose" in mind.kits[3] and case.diagnosis["evidence"].startswith("-rw-r--r--")


def test_every_case_has_a_report_a_person_reads_in_a_minute(tmp_path):
    from dbee.doctor import Case
    c = Case(id="c-2", patient="local", wake={"kind": "unit_failed", "what": "cron.service", "evidence": "status=203/EXEC"})
    c.looks = [{"cmd": "ls -lL /usr/sbin/cron", "code": 0, "out": "-rw-r--r-- 1 root root 60080 /usr/sbin/cron"}]
    c.diagnosis = {"cause": "cron's binary lost its execute bit", "evidence": "-rw-r--r-- 1 root root 60080"}
    c.cures = [{"cure": {"command": "chmod +x /usr/sbin/cron", "undo": "chmod -x /usr/sbin/cron", "verify": "systemctl is-active cron"},
                "code": 0, "verify_code": 0}]
    c.end, c.finding, c.mind, c.closed = "closed", "chmod +x restored it", "gemma-4-26b", c.opened + 95
    c.save(tmp_path)
    md = (tmp_path / "c-2.md").read_text()
    for want in ("closed", "cron.service", "status=203/EXEC", "lost its execute bit", "`chmod +x /usr/sbin/cron`",
                 "undo: `chmod -x /usr/sbin/cron`", "verify passed", "1 look", "gemma-4-26b", "c-2.json"):
        assert want in md, want
    assert len(md.splitlines()) < 40


def test_a_busy_hive_makes_the_case_wait_for_a_seat_not_end(tmp_path):
    # seen live: 31 cases on 12 seats; seven ended "no seat in 600s" though the case had hours left
    from dbee.minds import NoSeat

    class _Busy(_Script):
        def chat(self, msgs, tools=None, max_tokens=0, effort=""):
            if self.n == 1 and not getattr(self, "waited", 0):
                self.waited = 1
                raise NoSeat("no seat for qwen3.5-4b-iq4xs in 600s: every slot busy")
            return super().chat(msgs, tools, max_tokens, effort)
    mind = _Busy(("look", {"cmd": "ls -lL /usr/sbin/cron"}), READ, HAND)
    case = Doctor(_Patient(), mind, home=tmp_path).treat(Wake("unit_failed", "cron.service"), case_id="c-5")
    assert case.end == "handed" and case.diagnosis                 # it waited, then went on
