"""The Hive's probes are the doctor's own first looks for a wake about the drone."""
import base64

from dbee import platform as P
from dbee.doctor import Doctor
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
    first = Doctor(pt, mind=None, home=tmp_path)._first_look(Wake("health_miss", "http://127.0.0.1:4411/health"))
    assert "$ probe downtime\n[exit 1]\nRED: the drone runs as bee's own unit" in first
    assert "$ probe engine" in first and "$ probe mic" not in first


def test_a_wake_about_anything_else_runs_no_probe(tmp_path):
    pt = _Patient()
    first = Doctor(pt, mind=None, home=tmp_path)._first_look(Wake("unit_failed", "cron.service"))
    assert "$ probe" not in first and not any("base64 -d" in c for c in pt.ran)


def test_a_patient_the_drone_does_not_run_gets_no_probe(tmp_path):
    # a probe reads its own context: run by root beside the drone it would say "the drone runs as root"
    pt = _Patient()
    pt.runs_as_drone = False
    first = Doctor(pt, mind=None, home=tmp_path)._first_look(Wake("health_miss", "http://127.0.0.1:4411/health"))
    assert "$ probe" not in first
