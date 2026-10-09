"""A plain log file, followed by name: a critical line wakes DBee, and a rotation does not blind it."""
import os
from queue import Queue

from dbee.patient import Local
from dbee.watch import FileWatcher


def test_a_file_is_followed_across_rotation(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("ERROR: an old line, from before DBee watched\n")
    q: Queue = Queue()
    w = FileWatcher(Local(), q, str(log), r"ERROR|FATAL")
    w.start()
    assert w.ready.wait(10)
    with open(log, "a") as f:
        f.write("info: fine\nERROR: disk quota exceeded\n")
    wk = q.get(timeout=10)
    assert (wk.kind, wk.what) == ("line", str(log)) and "quota" in wk.evidence
    os.rename(log, tmp_path / "app.log.1")            # logrotate: the old file moves, a new one takes the name
    log.write_text("FATAL: cannot open socket\n")
    wk = q.get(timeout=10)
    assert "socket" in wk.evidence
    w.end()
    assert q.empty()                                    # the old line never woke it
