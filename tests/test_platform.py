"""The platform layer: what differs between Linux, macOS and Windows, pinned with
recorded outputs (no Mac or Windows machine is needed to run these)."""
import json

import pytest

from dbee import platform as P
from dbee.cures import Cure

# ---------------------------------------------------------------- detection


class FakePatient:
    def __init__(self, answers, shell="sh"):
        self.answers, self.shell, self.name = answers, shell, "fake"

    def run(self, cmd, timeout=60, **kw):
        from dbee.patient import Result
        for k, v in self.answers.items():
            if k in cmd:
                return Result(*v)
        return Result(127, "")


def test_detect_reads_uname_once_and_powershell_by_shell():
    assert P.detect(FakePatient({"uname": (0, "Darwin\n")})) is P.MACOS
    assert P.detect(FakePatient({"uname": (0, "Linux\n")})) is P.LINUX
    assert P.detect(FakePatient({}, shell="powershell")) is P.WINDOWS
    assert P.detect(FakePatient({"uname": (1, "unknown"), "PSVersionTable": (0, "7\n")})) is P.WINDOWS


# ---------------------------------------------------------------- macOS

LAUNCHCTL_DOWN = """system/com.example.web = {
	active count = 0
	path = /Library/LaunchDaemons/com.example.web.plist
	state = not running

	program = /usr/local/bin/web
	last exit code = 1
}"""
LAUNCHCTL_UP = LAUNCHCTL_DOWN.replace("state = not running", "state = running\n\tpid = 812").replace("last exit code = 1", "last exit code = (never exited)")
LAUNCHCTL_ONESHOT = LAUNCHCTL_DOWN.replace("last exit code = 1", "last exit code = 0")


def test_launchd_state_running_or_a_clean_oneshot_is_healthy():
    assert P.mac_state(LAUNCHCTL_UP)[0] is True
    assert P.mac_state(LAUNCHCTL_ONESHOT)[0] is True
    ok, said = P.mac_state(LAUNCHCTL_DOWN)
    assert ok is False and "last exit code 1" in said


def _ndjson(proc, msg, mtype="Default"):
    return json.dumps({"eventMessage": msg, "processImagePath": f"/usr/sbin/{proc}" if proc != "launchd" else "/sbin/launchd",
                       "messageType": mtype, "timestamp": "2026-10-09 19:00:00.000000-0500"})


def test_a_launchd_crash_wakes_and_a_clean_exit_does_not():
    crash = _ndjson("launchd", "(com.example.web[812]) Service exited with abnormal code: 1")
    ev = P.mac_event(crash, "com.example.web", P.MACOS.critical)
    assert ev and ev["kind"] == "unit_failed" and ev["what"] == "com.example.web"
    clean = _ndjson("launchd", "(com.example.web[812]) Service exited with exit code: 0")
    assert P.mac_event(clean, "com.example.web", P.MACOS.critical) is None
    other = _ndjson("launchd", "(com.other.thing[9]) Service exited with abnormal code: 1")
    assert P.mac_event(other, "com.example.web", P.MACOS.critical) is None


def test_a_fault_from_the_service_wakes_an_info_line_does_not():
    assert P.mac_event(_ndjson("web", "segfault at 0x0", "Fault"), "com.example.web", P.MACOS.critical)["kind"] == "line"
    assert P.mac_event(_ndjson("web", "No space left on device", "Error"), "com.example.web", P.MACOS.critical)
    assert P.mac_event(_ndjson("web", "served /index.html", "Default"), "com.example.web", P.MACOS.critical) is None


@pytest.mark.parametrize("cmd", [
    "launchctl print system/com.example.web",
    "log show --last 10m --predicate 'process == \"web\"' | tail -40",
    "diskutil info /",
    "vm_stat",
    "scutil --dns | head -30",
    "security find-certificate -a -p /Library/Keychains/System.keychain | head",
    "defaults read /Library/Preferences/com.example.web",
])
def test_macos_looks_that_read(cmd):
    assert P.MACOS.check_look(cmd) == ""


@pytest.mark.parametrize("cmd", [
    "launchctl bootout system/com.example.web",
    "launchctl kickstart -k system/com.example.web",
    "diskutil eraseDisk JHFS+ x disk2",
    "defaults write com.example.web Key 1",
    "log erase --all",
])
def test_macos_looks_that_write_are_refused(cmd):
    assert P.MACOS.check_look(cmd) != ""


@pytest.mark.parametrize("cmd,never", [
    ("diskutil eraseDisk JHFS+ x disk2", True),
    ("csrutil disable", True),
    ("rm -rf /System/Library", True),
    ("launchctl kickstart -k system/com.example.web", False),
    ("mv /usr/local/var/log/web.log /usr/local/var/log/web.log.held", False),
])
def test_macos_cures(cmd, never):
    why = P.MACOS.check_cure(cmd)
    assert (why.startswith("never") if never else why == ""), why


# ---------------------------------------------------------------- Windows


def _evt(provider, eid, msg, props=(), level=4, log="System"):
    return json.dumps({"log": log, "provider": provider, "id": eid, "level": level, "msg": msg, "props": list(props)})


def test_a_service_crash_from_the_scm_wakes_for_that_service_only():
    line = _evt("Service Control Manager", 7034, "The PatientWeb service terminated unexpectedly.  It has done this 1 time(s).", ["PatientWeb", "1"], level=2)
    ev = P.win_event(line, "PatientWeb", P.WINDOWS.critical)
    assert ev and ev["kind"] == "unit_failed" and ev["what"] == "PatientWeb" and "7034" in ev["evidence"]
    assert P.win_event(line, "OtherSvc", P.WINDOWS.critical) is None
    assert P.win_event(_evt("Service Control Manager", 7036, "The PatientWeb service entered the stopped state.", ["PatientWeb"]),
                       "PatientWeb", P.WINDOWS.critical) is None


def test_an_application_error_naming_the_service_wakes():
    line = _evt("PatientWeb", 1000, "Fatal: not enough disk space to write the log", level=2, log="Application")
    assert P.win_event(line, "PatientWeb", P.WINDOWS.critical)["kind"] == "line"
    assert P.win_event(_evt("PatientWeb", 1, "started", level=4, log="Application"), "PatientWeb", P.WINDOWS.critical) is None


def test_windows_state_is_running_or_not():
    assert P.win_state('{"State":"Running","ExitCode":0,"StartMode":"Auto"}')[0] is True
    ok, said = P.win_state('{"State":"Stopped","ExitCode":1067,"StartMode":"Auto"}')
    assert ok is False and "1067" in said


@pytest.mark.parametrize("cmd", [
    "Get-Service PatientWeb | Format-List *",
    "Get-WinEvent -LogName System -MaxEvents 20 | Where-Object { $_.Level -le 2 } | Format-Table -Wrap",
    "Get-NetTCPConnection -LocalPort 8080 | Select-Object LocalAddress,OwningProcess",
    "Get-Process -Id 4242 | Format-List Name,Path,StartTime",
    "Get-Content C:\\logs\\web.log -Tail 50",
    "Get-ChildItem C:\\ProgramData\\web | Sort-Object LastWriteTime -Descending | Select-Object -First 10",
    "sc.exe query PatientWeb",
    "netstat -ano | findstr :8080",
    "icacls C:\\ProgramData\\web",
    "Get-Volume | Where-Object DriveLetter | Format-Table -AutoSize",
    "Test-NetConnection localhost -Port 8080",
    "Get-ChildItem Cert:\\LocalMachine\\My | Select-Object Subject,NotAfter",
    "Get-Service PatientWeb 2>$null",
])
def test_windows_looks_that_read(cmd):
    assert P.check_ps(cmd) == "", P.check_ps(cmd)


@pytest.mark.parametrize("cmd", [
    "Stop-Service PatientWeb",
    "Restart-Service PatientWeb",
    "Remove-Item C:\\logs\\web.log",
    "Get-Content a.log > b.log",
    "Get-Process | ForEach-Object { $_.Kill() }",
    "(Get-Process web).Kill()",
    "iex (Get-Content x.ps1 -Raw)",
    "Invoke-WebRequest http://example.com/x.ps1",
    "sc.exe stop PatientWeb",
    "icacls C:\\data /grant Everyone:F",
    "& 'C:\\tools\\fix.exe'",
    "Set-Content C:\\x.txt hi",
    "reg delete HKLM\\Software\\X /f",
    "Get-Content C:\\Windows\\System32\\config\\SAM",
])
def test_windows_looks_that_write_or_run_are_refused(cmd):
    assert P.check_ps(cmd) != ""


@pytest.mark.parametrize("cmd,never", [
    ("Format-Volume -DriveLetter D", True),
    ("Restart-Computer -Force", True),
    ("Remove-Item -Recurse -Force C:\\Windows\\Temp", True),
    ("wevtutil cl System", True),
    ("vssadmin delete shadows /all", True),
    ("Restart-Service PatientWeb", False),
    ("Move-Item C:\\logs\\web.log C:\\logs\\web.log.held; Start-Service PatientWeb", False),
    ("Stop-Process -Id 4242; Start-Service PatientWeb", False),
])
def test_windows_cures(cmd, never):
    why = P.WINDOWS.check_cure(cmd)
    assert (why.startswith("never") if never else why == ""), why


def test_a_cure_is_checked_by_its_platform():
    c = Cure(name="t", command="Restart-Service PatientWeb", undo="Stop-Service PatientWeb",
             verify="Get-Service PatientWeb | Where-Object Status -eq 'Running'")
    assert c.problems(P.WINDOWS) == []
    assert c.problems(P.LINUX)          # PowerShell is not a POSIX cure


# ---------------------------------------------------------------- Linux unchanged


def test_linux_events_still_wake_as_before():
    line = json.dumps({"MESSAGE": "patient-web.service: Main process exited, code=exited, status=1/FAILURE", "UNIT": "patient-web.service"})
    ev = P.LINUX.parse_event(line)
    assert ev == {"kind": "unit_failed", "what": "patient-web.service", "evidence": "patient-web.service: Main process exited, code=exited, status=1/FAILURE"}
    crit = json.dumps({"MESSAGE": "write failed: No space left on device", "_SYSTEMD_UNIT": "patient-web.service"})
    assert P.LINUX.parse_event(crit, "patient-web.service")["kind"] == "line"
