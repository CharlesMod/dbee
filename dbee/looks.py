"""dbee.looks — the doctor's eyes: what it may read, and nothing it may write.

The shape is held in code, not asked of the mind: a look is one command from a
read-only family, with at most three filters after it. No redirection, no
command substitution, no `;`/`&&`/`||`, no flag the family lists as a write.
Output is cut to its tail so a mind reads what matters and the record stays
small. Ported from the hive's apiary.looks, without the hive.
"""
from __future__ import annotations

import re
import shlex

OUT_LINES = 80
OUT_CHARS = 6000

# family -> flags it may not say (the write-shaped ones)
FAMILIES: dict[str, tuple[str, ...]] = {
    "ps": (), "ss": (), "df": (), "free": (), "du": (), "id": (), "uptime": (), "uname": (),
    "lsblk": (), "findmnt": (), "hostname": (), "date": (), "nproc": (), "env": (), "last": (),
    "cat": (), "grep": (), "ls": (), "stat": (), "head": (), "tail": (), "wc": (), "file": (),
    "readlink": (), "realpath": (), "getent": (), "which": (), "find": ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"),
    "journalctl": ("--vacuum-size", "--vacuum-time", "--vacuum-files", "--rotate", "--flush", "--sync", "--relinquish-var"),
    "systemctl": ("start", "stop", "restart", "reload", "enable", "disable", "mask", "unmask", "kill",
                  "reset-failed", "set-property", "edit", "daemon-reload", "isolate", "poweroff", "reboot", "halt"),
    "ip": ("add", "del", "set", "flush", "change", "replace"), "lsof": (), "dmesg": ("-c", "-C", "--clear"),
    "ping": (), "curl": ("-X", "--request", "-d", "--data", "--data-binary", "-F", "--form", "-T", "--upload-file", "-o", "--output", "-O"),
    "loginctl": ("enable-linger", "disable-linger", "terminate-user", "kill-user", "lock-session", "terminate-session"),
    "pgrep": (), "fuser": ("-k", "-K", "--kill"), "lsusb": (), "lspci": (), "sysctl": ("-w", "--write"),
    "crontab": ("-e", "-r"), "mount": ("-o", "-a", "--bind", "--move"), "nginx": ("-s",), "sshd": (), "python3": ("-c", "-m"),
    "ulimit": (), "lscpu": (), "vmstat": (), "iostat": (), "top": ("-d",), "numfmt": (), "sort": (), "uniq": (), "cut": (), "awk": (), "sed": ("-i", "--in-place", "w", "e"),
    "test": (), "true": (), "echo": (), "printf": (), "stat": (), "md5sum": (), "sha256sum": (), "openssl": ("req", "genrsa", "genpkey", "rand"),
    "timedatectl": ("set-time", "set-timezone", "set-ntp", "set-local-rtc"), "hostnamectl": ("set-hostname", "set-icon-name", "set-chassis"),
    "nslookup": (), "dig": (), "host": (), "netstat": (), "resolvectl": ("flush-caches", "reset-statistics", "revert", "dns", "domain"),
}
FILTERS = {"grep", "tail", "head", "wc", "sort", "uniq", "cut", "awk", "sed", "tr", "jq", "numfmt", "column"}
SECRET = re.compile(r"(?i)(api[_-]?key|token|password|(?<![/\w])passwd(?!\b/)|secret|authkey|private[_-]?key|\.ssh/|id_(rsa|ed25519|ecdsa|dsa)\b|/etc/shadow|\.pem\b|\.key\b|tailscaled\.state|\.gnupg/|\.netrc|credentials)")


OPS = {";", "&&", "||", "|", "&", ">", ">>", "<", "<<", "(", ")", ">&", "<&", "&>", "|&"}


def segments(cmd: str) -> list[tuple[str, list[str]]]:
    """Split a shell line into (operator-before, tokens) by the shell's own
    quoting: a `;` or `|` inside quotes is part of a word, not an operator.
    Raises ValueError on unbalanced quotes."""
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|<>()")
    lx.whitespace_split = True
    out, cur, op = [], [], ""
    for tok in lx:
        if tok in OPS or (tok and set(tok) <= set(";&|<>()")):
            out.append((op, cur))
            cur, op = [], tok
        else:
            cur.append(tok)
    out.append((op, cur))
    return [(o, t) for o, t in out if t or o]


def check(cmd: str) -> str:
    """Why this look may not run, or '' when it may."""
    if not cmd.strip():
        return "empty"
    if "$(" in cmd or "`" in cmd:
        return "no command substitution in a look"
    try:
        segs = segments(cmd)
    except ValueError as e:
        return f"unparseable: {e}"
    if any(op not in ("", "|") for op, _ in segs):
        return "a look is one command and its filters: no redirection, `;`, `&&`, `||` or `&`"
    if len(segs) > 4:
        return "at most three filters after the command"
    head = segs[0][1]
    parts = [None] + [t for _, t in segs[1:]]
    if not head:
        return "empty"
    fam = head[0].rsplit("/", 1)[-1]
    if fam == "sudo":
        return "the doctor already runs as the patient's root; no sudo"
    if fam not in FAMILIES:
        return f"`{fam}` is not a read-only family a look may start with"
    for bad in FAMILIES[fam]:
        if bad in head[1:]:
            return f"`{fam} {bad}` writes; a look only reads"
    if fam in ("awk", "sed") and any(t for t in head[1:] if "system(" in t or ">" in t):
        return "no shell-outs or writes inside awk/sed"
    for fh in parts[1:]:
        if not fh or fh[0] not in FILTERS:
            return f"`{(fh or ['?'])[0]}` is not a filter a look may use (grep, tail, head, wc, sort, uniq, cut, awk, sed, tr, jq)"
        if fh[0] == "sed" and any(x in fh[1:] for x in ("-i", "--in-place")):
            return "sed -i writes"
    for t in head[1:]:
        if SECRET.search(t) and fam in ("cat", "grep", "head", "tail", "find", "ls", "stat"):
            return "a look does not read a secret's file by name"
    return ""


def cut(out: str) -> str:
    lines = out.splitlines()
    if len(lines) > OUT_LINES:
        lines = [f"[{len(lines) - OUT_LINES} earlier lines cut]"] + lines[-OUT_LINES:]
    s = "\n".join(lines)
    if len(s) > OUT_CHARS:
        s = f"[{len(s) - OUT_CHARS} chars cut]\n" + s[-OUT_CHARS:]
    return SECRET_VALUE.sub(r"\1=<masked>", s)


SECRET_VALUE = re.compile(r"(?i)\b((?:api[_-]?key|token|password|passwd|secret|authkey)[a-z_]*)\s*[=:]\s*\S+")


def look(patient, cmd: str, *, timeout: float = 30) -> tuple[int, str]:
    """Run one look on the patient. A refused look returns (126, why)."""
    why = check(cmd)
    if why:
        return 126, f"refused: {why}"
    r = patient.run(cmd, timeout=timeout)
    return r.code, cut(r.out)
