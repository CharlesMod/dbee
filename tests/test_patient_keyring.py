"""A sim patient takes no kernel key: many at once must not spend the user's keyring quota."""
import subprocess

from dbee import patient


def test_a_patient_starts_without_a_session_keyring(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(patient, "_podman", lambda: ["distrobox-host-exec", "podman"])
    seen = []

    def run(args, **kw):
        seen.append(args)
        if "run" in args:
            raise SystemExit   # stop once the container's start is seen
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(patient.subprocess, "run", run)
    p = patient.Podman("dbee-t")
    try:
        p.up("img")
    except SystemExit:
        pass
    start = next(a for a in seen if "run" in a)
    i = start.index("podman")
    assert start[:i] == ["distrobox-host-exec", "env", f"CONTAINERS_CONF_OVERRIDE={start[i - 1].split('=', 1)[1]}"]
    conf = start[i - 1].split("=", 1)[1]
    assert "keyring = false" in open(conf).read()


def test_the_sim_runs_only_as_many_patients_as_the_keyring_has_room_for():
    users = "    0:   100 99/99 95/1000000 1500/25000000\n 1000:    20 20/20 20/200 300/20000\n"
    assert patient.key_room(users, uid=1000) == (200 - 20) // patient.KEYS_PER_PATIENT
    assert patient.key_room("", uid=1000) is None          # unreadable: no cap claimed
    assert patient.key_room(" 1000:   200 200/200 200/200 9/20000\n", uid=1000) == 1   # one at a time, never none
