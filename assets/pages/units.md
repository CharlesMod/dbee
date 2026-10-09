# units

The hive runs on every frame as systemd user units. A frame's drone is the one template, ops/systemd/hive-drone.service, for every node that runs one as a user.
What the frame is (caps, slots, flags) and where the court lives are facts of the machine, in ~/.config/hive/node.env.
How a role yields is a drop-in in that role's directory, ops/systemd/<role>/hive-drone.service.d/ (the Queen's guest.conf).
A station runs its own system units, ops/station/units/.
The Queen's services (court, floor, veil, piping, antennae, estate) are units under ops/systemd/queen/.

## Routes, files, units
- install: the template into ~/.config/systemd/user/, the role's drop-in beside it, systemctl --user daemon-reload, enable --now hive-drone
- the drone unit: ExecStart ~/.hive/bin/drone --local --court $HIVE_COURT --slots $HIVE_SLOTS --work-dir ~/.hive/work --caps $HIVE_CAPS
- restart: Restart=always, RestartSec=2, RestartSteps=5, RestartMaxDelaySec=60, StartLimitIntervalSec=0 (it never gives up)
- caps on the drone: MemoryHigh=85% MemoryMax=90% MemorySwapMax=2G; the engines and jobs it runs are its children, under the same ceiling
- a station's drone: MemoryHigh=60% MemorySwapMax=256M
- no NoNewPrivileges on the drone: its installs run through the sudo rule its join wrote

## Invariants
- every hive-drone unit carries MemoryHigh, MemoryMax and MemorySwapMax
- no hive unit is failed, and none restarted 3 times in an hour
- one drone unit per frame
- journald runs and keeps each unit's log

## Known fault shapes
- uncapped: a drone installed before the caps runs without them (systemctl show hive-drone lacks MemoryHigh, MemoryMax or MemorySwapMax). Confirm: unit-caps (not yet a probe). Fix: a drop-in with the three lines, daemon-reload, a restart through the drone's drain; undo moves the drop-in away.
- crash-loop: a hive unit failed, or restarted 3 times in an hour. Confirm: unit-state (not yet a probe), and the unit's last 200 journal lines as evidence.
- journal-down: journald is down, so no unit's log is kept. Confirm: journal (not yet a probe).
