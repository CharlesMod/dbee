"""A user-domain scenario runs on its own OS, on the machine itself; a container one where podman is."""
from dbee import sim
from dbee.patient import Local, Podman


def test_a_scenario_runs_only_where_its_patient_lives(monkeypatch):
    monkeypatch.setattr(sim.sys, "platform", "darwin")
    monkeypatch.setattr(sim.shutil, "which", lambda n: None)
    assert sim.runnable_here({"patient": "macos-user"})
    assert not sim.runnable_here({"patient": "windows-user"})
    assert not sim.runnable_here({"patient": "ubuntu24"})          # no podman on this Mac
    monkeypatch.setattr(sim.sys, "platform", "linux")
    monkeypatch.setattr(sim.shutil, "which", lambda n: "/usr/bin/podman" if n == "podman" else None)
    assert sim.runnable_here({"patient": "ubuntu24"}) and not sim.runnable_here({"patient": "macos-user"})


def test_the_sim_owns_a_container_but_never_the_machine_it_runs_on():
    p, owned = sim.patient_for({"patient": "macos-user"}, "x")
    assert isinstance(p, Local) and not owned                     # never taken down
    p, owned = sim.patient_for({"patient": "ubuntu24"}, "dbee-x")
    assert isinstance(p, Podman) and owned


def test_the_mac_scenarios_are_found_on_a_mac(monkeypatch):
    monkeypatch.setattr(sim.sys, "platform", "darwin")
    names = {sc["name"] for sc in sim.scenarios(sim.ROOT / "scenarios", "t1")}
    assert {"mac-perms-config", "mac-bad-path", "mac-port-taken"} <= names
