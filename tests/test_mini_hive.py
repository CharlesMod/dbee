"""A scenario that needs a Hive runs only where a Hive build is (its court and drone)."""
from pathlib import Path

from dbee import sim


def _build(d: Path) -> Path:
    d.mkdir(parents=True)
    for b in ("court", "drone"):
        (d / b).write_text("#!/bin/sh\n")
    return d


def test_a_hive_scenario_is_skipped_where_no_hive_is_built(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.delenv("DBEE_HIVE_BIN", raising=False)
    monkeypatch.setattr(sim.shutil, "which", lambda n: "/usr/bin/podman" if n == "podman" else None)
    sc = {"name": "x", "patient": "ubuntu24", "needs": ["root", "hive"]}
    assert sim.hive_bin() is None and not sim.runnable_here(sc)
    assert sim.runnable_here({**sc, "needs": ["root"]})
    monkeypatch.setenv("DBEE_HIVE_BIN", str(_build(tmp_path / "hivebin")))
    assert sim.hive_bin() == tmp_path / "hivebin" and sim.runnable_here(sc)


def test_the_box_units_point_the_drone_at_the_box_court():
    court = (sim.HIVE_UNITS / "hive-court.service").read_text()
    drone = (sim.HIVE_UNITS / "hive-drone.service").read_text()
    assert "--listen 127.0.0.1:4410" in court and "HIVE_TRUST=off" in court
    assert "--court http://127.0.0.1:4410" in drone and "--node box" in drone
