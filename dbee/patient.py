"""dbee.patient — the machine the doctor works on, reached one way.

A Patient runs a command and returns (exit code, output). Three kinds:
``Local`` (this host), ``Podman`` (a container, `podman exec`, through
`distrobox-host-exec` when podman lives on the host and we do not), ``Ssh``.
The doctor never knows which: looks, cures and watchers all go through
``run`` and ``stream``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from waspdoctor.patient import PS_PRELUDE, Hive, Patient  # noqa: F401  (a Hive frame, reached as every product does)
from waspdoctor.protocol import Result  # noqa: F401  (the loop's shape)



class Local(Patient):
    name = "local"

    def __init__(self):
        import os
        self.shell = "powershell" if os.name == "nt" else "sh"

    def argv(self, cmd, user="root", interactive=False):
        if self.shell == "powershell":
            return ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd]
        return ["sh", "-c", cmd]


class Ssh(Patient):
    """A machine over OpenSSH. `shell="powershell"` for a Windows host (its
    OpenSSH default shell may be cmd: the command is handed to PowerShell)."""

    def __init__(self, host: str, shell: str = "sh"):
        self.host = host
        self.name = host
        self.shell = shell

    def argv(self, cmd, user="root", interactive=False):
        base = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.host]
        if self.shell == "powershell":
            import base64
            enc = base64.b64encode((PS_PRELUDE + cmd).encode("utf-16-le")).decode()
            return base + [f"powershell -NoProfile -NonInteractive -OutputFormat Text -EncodedCommand {enc}"]
        return base + [cmd]


def _podman() -> list[str]:
    if shutil.which("podman"):
        return ["podman"]
    if shutil.which("distrobox-host-exec"):
        return ["distrobox-host-exec", "podman"]
    raise RuntimeError("no podman here or on the host")


KEYS_PER_PATIENT = 6     # measured: systemd's 5 in a booted patient, plus a margin


def key_room(key_users: str, uid: int) -> int | None:
    """How many more patients the user's kernel keyring quota holds, from /proc/key-users
    (``uid: usage nkeys/nikeys qnkeys/maxkeys qnbytes/maxbytes``); None when unread."""
    for line in key_users.splitlines():
        f = line.split()
        if f and f[0] == f"{uid}:" and len(f) >= 5:
            used, cap = (int(x) for x in f[3].split("/"))
            return max(1, (cap - used) // KEYS_PER_PATIENT)
    return None


def patient_room() -> int | None:
    try:
        return key_room(Path("/proc/key-users").read_text(), os.getuid())
    except OSError:
        return None


class Podman(Patient):
    def __init__(self, container: str):
        self.container = container
        self.name = container
        self.pm = _podman()

    def argv(self, cmd, user="root", interactive=False):
        return [*self.pm, "exec", *(["-i"] if interactive else []), "-u", user, self.container, "sh", "-c", cmd]

    # --- the simulator's side: a throwaway patient's life ---
    def up(self, image: str, *, mem: str = "1g", disk_mb: int = 0) -> None:
        """Start a systemd container. ``disk_mb`` gives / a small tmpfs root overlay
        bound so disk-full faults are honest and quick to seed."""
        subprocess.run([*self.pm, "rm", "-f", self.container], capture_output=True)
        # no session keyring: each container's key spends the user's kernel quota
        # (200 keys), and a wide sim then fails with "keyctl: Disk quota exceeded"
        conf = Path.home() / ".cache" / "dbee" / "podman-nokeyring.conf"
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text("[containers]\nkeyring = false\n")
        args = [*self.pm[:-1], "env", f"CONTAINERS_CONF_OVERRIDE={conf}", self.pm[-1], "run", "-d", "--name", self.container, "--systemd=always",
                "--memory", mem, "--hostname", self.container,
                "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/run/lock"]
        if disk_mb:
            # a small writable /var/log so "the disk fills" means this, not the host
            args += ["--tmpfs", f"/var/log/patient:size={disk_mb}m,mode=0755"]
        args += [image]
        p = subprocess.run(args, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"podman run: {p.stderr.strip()}")
        # systemd up
        for _ in range(60):
            r = self.run("systemctl is-system-running 2>/dev/null", timeout=10)
            if r.out.strip() in ("running", "degraded"):
                return
            import time
            time.sleep(0.5)
        raise RuntimeError(f"{self.container}: systemd did not come up: {r.out.strip()}")

    def down(self) -> None:
        subprocess.run([*self.pm, "rm", "-f", "-t", "2", self.container], capture_output=True)

    def copy_in(self, src: str, dst: str) -> None:
        p = subprocess.run([*self.pm, "cp", src, f"{self.container}:{dst}"], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"podman cp: {p.stderr.strip()}")
