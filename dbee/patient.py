"""dbee.patient — the machine the doctor works on, reached one way.

A Patient runs a command and returns (exit code, output). Three kinds:
``Local`` (this host), ``Podman`` (a container, `podman exec`, through
`distrobox-host-exec` when podman lives on the host and we do not), ``Ssh``.
The doctor never knows which: looks, cures and watchers all go through
``run`` and ``stream``.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Result:
    code: int
    out: str

    @property
    def tail(self) -> str:
        return self.out[-6000:]


class Patient:
    name = "patient"

    def argv(self, cmd: str, user: str = "root", interactive: bool = False) -> list[str]:
        raise NotImplementedError

    def run(self, cmd: str, *, timeout: float = 60, user: str = "root", input: str | None = None) -> Result:
        try:
            p = subprocess.run(self.argv(cmd, user, interactive=input is not None), capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=timeout, input=input,
                               stdin=None if input is not None else subprocess.DEVNULL)
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            return Result(124, out + f"\n[timed out after {timeout:.0f}s]")
        out = p.stdout + (("\n" + p.stderr) if p.stderr else "")
        return Result(p.returncode, out)

    def stream(self, cmd: str) -> subprocess.Popen:
        """A long-running command whose stdout is read line by line (journalctl -f)."""
        return subprocess.Popen(self.argv(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1, stdin=subprocess.DEVNULL)


class Local(Patient):
    name = "local"

    def argv(self, cmd, user="root", interactive=False):
        return ["sh", "-c", cmd]


class Ssh(Patient):
    def __init__(self, host: str):
        self.host = host
        self.name = host

    def argv(self, cmd, user="root", interactive=False):
        return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.host, cmd]


def _podman() -> list[str]:
    if shutil.which("podman"):
        return ["podman"]
    if shutil.which("distrobox-host-exec"):
        return ["distrobox-host-exec", "podman"]
    raise RuntimeError("no podman here or on the host")


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
        args = [*self.pm, "run", "-d", "--name", self.container, "--systemd=always",
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
