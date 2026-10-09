"""dbee.cures — what the doctor may do to a patient, and the shape every act keeps.

A cure is a command with an undo and a verify. Two sources:

* the **runbook** (``assets/runbook.jsonl``): named cures with a signature (which
  probe reads red), a script, an undo script and a verify probe. These are
  rules someone chose; the doctor runs one when its signature matches.
* a **written** cure: the mind names a command, its undo and a verify command.
  Allowed only inside the shape below; recorded (with its undo) before it runs.

The shape, held in code: a cure is one line of shell from the ``ALLOWED``
verbs; nothing in ``NEVER`` (the irreversible: wiping, reboots, filesystems,
devices, users, the doctor's own records); its undo is non-empty and passes the
same check; its verify is a read-only look (``looks.check``). What the shape
refuses is refused however the mind words it.
"""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from . import looks

NEVER = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f?|-[a-zA-Z]*f[a-zA-Z]*r)\s+(/|/\*|/etc|/var|/usr|/home|/boot|/root|/opt|/srv|/lib|/bin|/sbin)(\s|$|/\*)"), "a recursive delete of a system tree"),
    (re.compile(r"\brm\s+.*\s/var/log(\s|$|/\*$)"), "deleting the log tree; truncate the file instead"),
    (re.compile(r"\b(reboot|shutdown|halt|poweroff|init\s+[06]|systemctl\s+(reboot|poweroff|halt|kexec|isolate))\b"), "a reboot or power change"),
    (re.compile(r"\b(mkfs|fdisk|parted|wipefs|sfdisk|blkdiscard|mkswap)\b"), "a filesystem or partition write"),
    (re.compile(r"\bdd\b.*\bof=/dev/"), "writing a device"),
    (re.compile(r"(^|[\s;&|])(userdel|groupdel|passwd|chpasswd|usermod\s+-p)\b"), "a user or password change"),
    (re.compile(r"\bfind\b.*\s-delete\b"), "find -delete sweeps whatever matches; name the files"),
    (re.compile(r"\bchmod\s+(-R\s+)?[0-7]*[0-7]{3}\s+/(\s|$)"), "chmod of /"),
    (re.compile(r"\bchown\s+-R\s+\S+\s+/(\s|$)"), "chown -R of /"),
    (re.compile(r"\bkill\s+(-9\s+|-KILL\s+)?1(\s|$)"), "killing PID 1"),
    (re.compile(r"\b(curl|wget)\b.*\|\s*(sh|bash)\b"), "piping the network into a shell"),
    (re.compile(r"/etc/(shadow|sudoers|ssh/sshd_config)\b"), "the machine's keys to itself"),
    (re.compile(r"\bcrontab\s+-r\b"), "removing every cron entry"),
    (re.compile(r"\b(iptables|nft)\s+.*(-F|flush)\b"), "flushing the firewall"),
    (re.compile(r"\b(tailscale|systemctl\s+\w+\s+tailscaled)\b"), "the tailnet: a doctor never cuts its own way in"),
    (re.compile(r"\.dbee/|dbee/cases"), "the doctor's own records"),
    (re.compile(r"\btruncate\b.*\s/(etc|usr|bin|sbin|lib|boot)/"), "truncating a system file"),
    (re.compile(r"(>|>>)\s*/dev/(sd|nvme|vd|hd|mapper)"), "writing a device"),
]
ALLOWED = {"systemctl", "truncate", "rm", "mv", "cp", "ln", "mkdir", "chmod", "chown", "chgrp", "touch", "kill", "pkill", "killall",
           "logrotate", "journalctl", "sed", "tee", "echo", "printf", "sh", "sync", "ip", "resolvectl", "timedatectl",
           "apt-get", "dpkg", "pip", "python3", "nginx", "sshd", "cron", "service", "sysctl", "ulimit", "swapoff", "swapon",
           "fuser", "umount", "mount", "fallocate", "gzip", "xz", "zstd", "tar", "find", "loginctl", "hostnamectl", "crontab", "ln", "cat", "test", "sleep", "true"}
FORBIDDEN_FOR = {"rm": ("-r", "-R", "-rf", "-fr", "--recursive"), "find": ("-exec", "-execdir", "-ok", "-delete"), "kill": ("-9", "-KILL", "-SIGKILL")}


def check_cure(cmd: str) -> str:
    """Why this command may not be a cure, or ''."""
    if not cmd.strip():
        return "empty"
    if "\n" in cmd.strip():
        return "a cure is one line"
    if "$(" in cmd or "`" in cmd:
        return "no command substitution in a cure"
    for pat, why in NEVER:
        if pat.search(cmd):
            return f"never: {why}"
    # each simple command (split on ; && || |) must start with an allowed verb
    for seg in re.split(r"\s*(?:;|&&|\|\||\|)\s*", cmd):
        seg = seg.strip()
        if not seg:
            continue
        # strip leading env assignments and redirections
        try:
            toks = shlex.split(seg)
        except ValueError as e:
            return f"unparseable: {e}"
        toks = [t for t in toks if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)]
        if not toks:
            continue
        verb = toks[0].rsplit("/", 1)[-1]
        if verb == "sudo":
            return "the doctor already runs as root; no sudo"
        if verb not in ALLOWED and verb not in looks.FAMILIES:
            return f"`{verb}` is not a verb a cure may use"
        for bad in FORBIDDEN_FOR.get(verb, ()):
            if bad in toks[1:]:
                return f"`{verb} {bad}` is not allowed in a cure (do it file by file, or SIGTERM first)"
    return ""


@dataclass
class Cure:
    name: str                 # a runbook name, or "written:<digest>"
    command: str
    undo: str
    verify: str               # a read-only look; exit 0 = the fault is gone
    why: str = ""
    source: str = "written"   # "runbook" | "written" | "casebook"
    page: str = ""

    def problems(self) -> list[str]:
        out = []
        if (w := check_cure(self.command)):
            out.append(f"command: {w}")
        if not self.undo.strip():
            out.append("undo: a cure without an undo is not a cure")
        elif (w := check_cure(self.undo)):
            out.append(f"undo: {w}")
        if not self.verify.strip():
            out.append("verify: a cure names how it will be checked")
        elif (w := looks.check(self.verify)):
            out.append(f"verify must be a read-only look: {w}")
        return out


@dataclass
class Runbook:
    rows: list[dict] = field(default_factory=list)
    root: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "Runbook":
        rb = cls(root=path.parent)
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    rb.rows.append(json.loads(line))
        return rb

    def matching(self, signature: list[str]) -> list[Cure]:
        """Runbook cures whose signature probe reads red in this case."""
        out = []
        for r in self.rows:
            sig = r.get("signature") or {}
            key = f"{sig.get('probe')}={sig.get('exit')}"
            if key in signature:
                out.append(Cure(name=r["name"], command=r.get("command") or self._script(r.get("script")),
                                undo=r.get("undo") or self._script(r.get("undo_script")),
                                verify=r.get("verify_cmd") or "", why=r.get("does", ""), source="runbook",
                                page=r.get("page", "")))
        return out

    def _script(self, name: str | None) -> str:
        if not name or not self.root:
            return ""
        p = self.root / "fixes" / name
        return f"sh /opt/dbee/fixes/{name}" if p.exists() else ""
