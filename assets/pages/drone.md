# drone

The drone is the worker on every frame (Go, swarm/drone). It pulls jobs from the court, runs them, and reports their exit codes and logs.
It serves what its config names (GET /v1/drones/{node}/config) on :4411, the engine's port.
It replaces its own binary from the release channel and keeps the last good one as drone.prev.
It follows the seat: the court it reaches is written to its seat file, ~/.hive/seat (HIVE_SEAT_FILE names another).

## Routes, files, units
- to the court: POST /v1/pull with its advertisement (its capabilities, its volumes, its slots derived, cap and effective, its capacity per class); POST /v1/jobs/{id}/heartbeat; POST /v1/jobs/{id}/complete; PUT /v1/honey/{digest} for logs
- slots: effective is the least of derived and the cap (swarm/drone/slots.go)
- a 409 on a heartbeat naming stale_reign or standby means the seat moved: the drone follows it and keeps the job (swarm/drone/job.go, seatMoved)
- upgrade: a fresh binary stays on probation until its first good poll; one that never confirmed a good boot is rolled back to drone.prev (swarm/drone/main.go)
- a job runs in its own process group; a cancel kills the group
- unit: hive-drone (the units page); binary ~/.hive/bin/drone, work dir ~/.hive/work

## Invariants
- a drone advertises its own node:<name> tag and never a loopback endpoint
- a busy drone still follows a seat move within 10 s
- a drone holding a running job is restarted only through its drain
- a frame with 0 jobs active advertises at least one effective slot
- every drone runs the binary the last rollout published, 10 min after it

## Known fault shapes
- silent-frame: the court lists the frame silent: its drone does not reach the court, its jobs abscond, and no job (no frame probe, no fix) can land there. Confirm: silent (a court probe: the last heartbeat, the absconded jobs, ping and the advertised ports from outside). Fix: none from here; a person at the machine restarts the drone, so consult with what the silent probe says they must check.
- no-linger: the drone is the user's own unit and the account does not linger, so after a reboot (power lost, an update) or a logout nothing starts it: the frame answers ping and every port refuses. Seen 2026-10-04: sprinter stayed silent after a power event that rebooted it and pi-den, whose system-unit drone came back by itself. Confirm: downtime (on the frame, once someone has started it again). Fix: linger (runbook).
- jobs-lost: drones abandoned their jobs on a 409 at a seat move. Confirm: jobs-lost (not yet a probe). Fix: code.
- follow-late: a busy drone followed the seat 40 s late. Confirm: drone-follow (not yet a probe). Fix: code.
- suspect: a frame flagged SUSPECT though seen under 30 s ago. Confirm: suspect (not yet a probe). Fix: code.
- slots-zero: a frame advertising 0 effective slots with 0 jobs active, so no job runs there. Confirm: slots-zero (not yet a probe). Fix: code.
- not-converged: a drone's binary not converged 10 min after a rollout. Confirm: rollout (not yet a probe).
- uncapped: see the units page.
