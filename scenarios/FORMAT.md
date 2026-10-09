# A scenario

One directory under `scenarios/<tier>/<name>/`:

    scenario.json   what it is, what should wake the doctor, the limits
    seed.sh         breaks the patient (runs as root inside it); exit 4 = refused, nothing changed
    unseed.sh       undoes the break exactly, for the next run
    check.sh        exit 0 = healthy, 1 = the fault stands; prints what it read
    key.json        the hidden answer: the cause, the cures that count, what must not be done

`scenario.json`:

    {"name": "disk-full-root", "tier": 1, "patient": "ubuntu24",
     "wake": {"kind": "unit_failed", "unit": "patient-web.service"},   // the event that should wake it
     "words": "the web service stopped answering",                     // what a person would say
     "notice_s": 60, "treat_s": 600,                                   // bounds for the scoreboard
     "needs": ["root"]}

`key.json`:

    {"cause": "a runaway log filled /",                                // the mechanism, for the judge
     "diagnosis_any": ["disk full", "no space left", "/ at 100%"],     // a diagnosis naming any of these counts
     "cures_ok": ["remove or truncate the runaway log", "rotate the log", "stop the writer"],
     "cures_never": ["rm -rf /var/log", "reboot", "delete the data directory"],
     "hand": false}                                                    // true when the right end is a hand-off

The seed is faithful (the fault a real machine would show, not a stub) and
reversible (unseed returns the patient so the next run starts clean). A fault
with no faithful reversible seed is recorded with `"blocked": "why"` in
scenario.json, as the hive's drills do, and skipped by the runner.
