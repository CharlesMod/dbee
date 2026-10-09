# quarantine

The court quarantines an action that crashed its retries away: a job whose lease lapsed on a live drone again and again (hive/court/reaper.go), recorded by its cache key, the action's identity (its command, its class, what it needs). A submit of the same action is refused with 409 quarantined until it is released.
The doctor triages each held action and reintroduces the ones whose cause is gone. A release can be undone: the next crash quarantines the action again.

## Routes, files, units
- GET /v1/quarantine: each held action, with its key, job, reason, when, the frame it last ran on, its class and its command
- POST /v1/quarantine/release {key, case, why}: one action out, with a quarantine_released event on the spine naming who, the case and why
- the spine's abscond and poison events for the job: how each attempt ended and what it implicated
- on the Queen's box, `court quarantine --db …` lists and `--clear KEY` releases, through the same function

## Invariants
- an action is quarantined only after its attempts lapsed on a drone that stayed up; a drone that restarted under the job is not the job's fault
- every release names its case and why, and lands on the spine
- the doctor releases only a key its own quarantine probe named

## Known fault shapes
- died-under: the frame's drone started again while the job held it (a reboot, a restart, an update, or the job itself stopping its drone, as a launch that pauses its frame does): the frame died under the job, and the action did not crash. Confirm: quarantine (the tail says the drone started again under the job). Fix: release once the frame is live, saying what stopped it.
- crasher: the command fails on every attempt and on more than one frame, or its own log says why: the quarantine is doing its job. Confirm: quarantine (several attempts, implicates job, no drone start under them). Fix: none by release; code the change that ends the crash, or consult; the case closes when the action is released after the fix.
- frame-sick: the action crashed only on this frame while it runs elsewhere: the frame is the fault (a disk, a driver, a missing tool). Confirm: quarantine, then the frame's own probes (disk, engine, organ). Fix: the frame's runbook fix, then release.
- stale: the action will never be asked again (a one-off, a superseded build): nothing waits on it. Confirm: quarantine. Fix: release with that why, so the quarantine holds only live faults.
