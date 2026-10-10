# The mini-Hive in a box

A scenario that `needs` `hive` gets a Hive of its own inside its patient: the Hive's
real court and drone (this machine's build, `DBEE_HIVE_BIN` or the `court` and
`drone` on the PATH or in `~/hive/bin`), as the units here, the court on loopback
with trust off (a box with no tailnet), the drone enrolled with it as the frame
`box`. The sim lays it after the patient is up and before the scenario's first
check; a machine with no Hive build skips those scenarios.
