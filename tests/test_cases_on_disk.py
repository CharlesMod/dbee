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
            return Result(0, "ELF 64-bit LSB pie executable")
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
