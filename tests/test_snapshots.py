"""A cure's targets are copied before it runs, on any platform, where the doctor may write."""
import os

from waspdoctor import platform as P
from waspdoctor.doctor import Case, Doctor
from dbee.patient import Local, Result


def test_a_target_is_kept_and_restored_with_no_gnu_stat_and_no_root(tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "stat").write_text("#!/bin/sh\necho 'stat: illegal option -- c' >&2\nexit 1\n")   # macOS's BSD stat
    (bin_ / "stat").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))                                 # a user install: no /var/lib
    conf = tmp_path / "app.conf"
    conf.write_text("port=8080\n")
    doc = Doctor(Local(), None, home=tmp_path / "dbee-home")
    case = Case(id="c-s", patient="local", wake={})
    assert doc._snapshot(case, 1, [str(conf)]) == [str(conf)]
    conf.write_text("broken\n")
    doc._restore(case, 1)
    assert conf.read_text() == "port=8080\n"
    assert str(tmp_path / "home") in case.snapshots[0]["copy"]


class _Win:
    name = "win"
    shell = "powershell"
    platform = P.WINDOWS

    def __init__(self):
        self.ran = []

    def run(self, cmd, *, timeout=60, user="root", input=None):
        self.ran.append(cmd)
        return Result(0, "kept C:\\Users\\u\\AppData\\Local\\DBee\\snap\\c-w\\1\\0\r\n")


def test_a_powershell_cure_names_its_targets_and_they_are_copied_first(tmp_path):
    w = _Win()
    doc = Doctor(w, None, home=tmp_path)
    cmd = r"Remove-Item 'C:\app\cache.db'; Set-Content -Path C:\app\app.conf -Value 'port=8080'"
    paths = doc._targets(cmd)
    assert paths == [r"C:\app\cache.db", r"C:\app\app.conf"]
    case = Case(id="c-w", patient="win", wake={})
    assert doc._snapshot(case, 1, paths) == paths
    assert all("Copy-Item" in c and "LOCALAPPDATA" in c for c in w.ran)
    assert case.snapshots[0]["copy"] == r"C:\Users\u\AppData\Local\DBee\snap\c-w\1\0\cache.db"
    doc._restore(case, 1)
    assert w.ran[-1].startswith("Copy-Item -LiteralPath 'C:\\Users") and "-Destination 'C:\\app\\app.conf' -Force" in w.ran[-1]
