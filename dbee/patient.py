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


@dataclass
class Result:
    code: int
    out: str

    @property
    def tail(self) -> str:
        return self.out[-6000:]


# PowerShell run without a console wraps its progress and error streams in CLIXML;
# a doctor reads text: progress off, errors as plain lines, wide output not cut
PS_PRELUDE = ("$ProgressPreference='SilentlyContinue'; $ErrorView='NormalView'; "
              "$PSDefaultParameterValues['Out-String:Width']=220; ")


class Patient:
    name = "patient"
    shell = "sh"
    _platform = None

    @property
    def platform(self):
        """What this machine is (Linux, macOS, Windows), asked once and kept."""
        if self._platform is None:
            from .platform import detect
            self._platform = detect(self)
        return self._platform

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


class Hive(Patient):
    """A frame of the Hive, reached the Hive's own way: each command is a job
    (`hive run FRAME LINE`), its exit the job's. `shell="powershell"` reaches the
    Windows side of a frame whose drone runs in WSL, through WSL's interop.
    Jobs end, so a Hive patient can be looked at and treated but not streamed:
    its watcher is the Hive's own spine."""

    PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    DONE = __import__("re").compile(r"^\S+: (succeeded|failed|cancelled|timed out)[^\n]*?exit (-?\d+)[^\n]*\(job \w+\)\s*$", __import__("re").M)

    runs_as_drone = True              # `hive run` runs as the frame's drone: its probes read true here

    def __init__(self, frame: str, shell: str = "sh", hive: str = ""):
        import shutil
        self.frame, self.name, self.shell = frame, frame, shell
        self.hive = hive or shutil.which("hive") or "hive"

    def argv(self, cmd, user="root", interactive=False):
        if self.shell == "powershell":
            import base64
            enc = base64.b64encode(PS_PRELUDE.__add__(cmd).encode("utf-16-le")).decode()
            cmd = f"{self.PS} -NoProfile -NonInteractive -OutputFormat Text -EncodedCommand {enc}"
        return [self.hive, "run", self.frame, cmd]

    def run(self, cmd, *, timeout=60, user="root", input=None):
        r = super().run(cmd, timeout=timeout + 30, user=user)
        m = None
        for m in self.DONE.finditer(r.out):
            pass
        if not m:
            return r
        out = (r.out[:m.start()] + r.out[m.end():]).rstrip("\n")
        return Result(int(m.group(2)), out)

    def stream(self, cmd):
        raise RuntimeError("a Hive patient is not streamed: watch it through the Hive's spine")
