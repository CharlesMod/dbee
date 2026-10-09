# queen

The Queen is the always-on frame that seats the court and honey; which frame it is, is the court's answer (GET /v1/queen names the seat).
The court keeps its database at ~/hive-home/court.sqlite and honey, its blob store, beside it in ~/hive-home/honey-store.
~/hive-home is also the self's home (Rocky's memory, settings and the bees' stores), snapshotted to honey every 5 minutes.
The Queen also runs the floor and the veil, and her drone runs jobs as a guest beside them.
When the Queen is dark the princess holds the seat in regency; a dark Queen cannot probe herself.

## Routes, files, units
- court: :4410 on HIVE_BIND, unit hive-court (ops/systemd/queen/hive-court.service), caps MemoryHigh=1536M MemoryMax=2G MemorySwapMax=512M
- floor: :4412 on loopback, unit melissa-floor, caps MemoryHigh=8G MemoryMax=12G MemorySwapMax=2G
- veil: :4414 on the tailnet, unit melissa-veil, caps MemoryHigh=2G MemoryMax=4G MemorySwapMax=1G
- also melissa-piping, melissa-antennae, melissa-estate, hive-litestream, queen-power
- drone: hive-drone with the queen drop-in guest.conf (Nice=19, IOSchedulingClass=idle)
- disks: / and ~/hive-home/honey-store; a drone advertises its volumes and their free space on every pull

## Invariants
- root and honey each under 85% full
- every hive unit runs under its memory caps
- the court, the floor and the veil answer on their ports
- the link is up and its DHCP lease is held

## Known fault shapes
- disk-full: root or honey over 85% (the root once reached 90%). Confirm: probe disk (exit 1, the df row over 85% in its tail). Fix: the undertaker's bury moves what its survey names into the morgue (hive undertaker bury); nothing is freed until purge, past the grace.
- frozen: a full disk, swap, journald and a Failed link together left the Queen dark and her lease lost. Confirm: probe disk and link from the princess. Fix: a power cycle, which only the keeper does; then the disk.
- link-down: networkctl shows the link Failed, or the DHCP lease runs under an hour. Confirm: link (not yet a probe). Fix: the keeper's.
