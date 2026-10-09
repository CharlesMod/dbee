# Findings

What the simulator has taught about driving each mind. Newest first. A row is
one run; the record is under `runs/<scenario>/<mind>/cases/`.

## 2026-10-09 — the installer driven through on three machines: what hid the faults

The end-to-end runs (DBee Setup installs, a real fault, a case, an uninstall)
found five faults in the harness and none that a sim would have shown:

- **macOS: launchd's exits are not in the unified log** on macOS 26. `log
  stream --process launchd` printed nothing for 30 s while an agent exited 1
  every 10 s, and `log show` held none either. They are in launchd's own log,
  `/var/log/com.apple.xpc.launchd/launchd.log` (world-readable); `tail -F`
  delivers each line the second it is written. After the fix the Mac's case
  woke, read, diagnosed `chmod 000` on the config and cured it in 5 turns
  (the 4B, local).
- **Windows: the Service Control Manager names a service by its display
  name**, so every SCM event for a service with its own display name was
  dropped. The limited task token was not the cause: it reads and subscribes
  to the System log, measured.
- **Any OS: a fault before the subscription is never seen.** The watch now
  waits for each stream to be subscribed and reads each named service once.
- **A slow mind was cut off by length, not silence**: a CPU-only 4B reads a
  4.6k prompt for over 3 minutes; the call now streams with a 120 s silence
  watchdog.
- **The Linux container hides the decisive line.** In a podman `--systemd`
  container, systemd's own exec failure (`Unable to locate executable
  '/usr/sbin/cron': Permission denied`) never reaches the journal; only
  `status=203/EXEC` does. The 4B, seeing that and `ExecStart=... $EXTRA_OPTS`,
  blamed the unset variable over 9 turns. The first looks now show the
  program's mode (`ls -lL`), which a real host's journal would also have
  implied. A Linux score on a fault of exec permissions in that container is
  partly the container's.

- **Grounding let a guess through.** The rerun put the program's mode in
  the 4B's first looks (`-rw-r--r-- /usr/sbin/cron`) and it still blamed
  `$EXTRA_OPTS` from turn 1, which is the model's miss: systemd's own status
  line puts `$EXTRA_OPTS` beside `status=203/EXEC`. Its diagnosis quoted
  evidence it had never read, was refused twice, and was recorded on the third
  try, because grounding allowed two refusals. Now no ungrounded diagnosis is
  ever recorded: after three, the case is handed to a person.

Cases are now written after every turn and export as training data (`dbee
export`); the Linux case above was lost because it was only written at its end.

## 2026-10-09 — every Linux look refused after M1 (a harness bug, fixed)

From the M1 platform commit (89af5d7, 14:11) until this fix, the Linux
platform's look families were an empty table rather than unset, and
`looks.check` read an empty table as "no verb is allowed". Every look and every
verify on a Linux patient was refused ("`systemctl` is not on the doctor's
read-only list"). Found live: DBee Setup in a container, cron broken, the 4B
proposing the right verify (`systemctl is-active cron`) round after round. A
Linux sim score taken between those times measures the bug, not the mind;
re-run before comparing. Pinned by
`test_ordinary_looks_and_verifies_pass_on_every_platform`.

## 2026-10-09 — disk-full-root, gemma-4-26b-a4b (the hive's brain, 3 × 32k on a 5080)

| run | woke | looks | cures | result | time | tokens | note |
|---|---|---|---|---|---|---|---|
| 1 | 0.5 s | 1 | 1 | fixed | 15 s | 16.8k | 3 cures refused first: undo given as `#` / `none` |
| 2 | 0.6 s | 5 | 2 | fixed | 18 s | 25.1k | fake undo `echo "No undo"` slipped the shape; re-read raced the unit's restart backoff |
| 3 | 0.6 s | 8 | 2 | **not fixed** (stalled) | 51 s | 40.9k | told to prefer a reversible `mv`, it moved the log aside on the full tmpfs: nothing freed |

- **Wake and diagnosis are not the problem.** All three woke on the journald
  event in under a second and named the mechanism (the full tmpfs, the
  service dying on its log write) from one or two looks.
- **The undo is where the 26B is weak.** It knows truncation has no undo and
  says so (`#`, `none`, `echo "No undo"`); a shape that refuses that makes it
  invent one. The shape now accepts `none: <why>` and counts it, and refuses
  no-op undos (echo, true, sleep).
- **A rule stated too simply is followed too simply** (run 3). "Prefer a move
  over a truncate" is right in general and wrong on a full filesystem; the
  26B did not reason past the rule when the verify came back red (df still
  100%), and spent its second cure removing the file its own undo had just
  moved back. The prompt now carries the nuance; the better fix is
  structural: show the mind the verify's *numbers* beside the rule.
- **The harness raced a restart.** `systemctl is-active` read `activating`
  (restart backoff) as red right after a good cure; the re-read now waits for
  the unit to settle (bounded 20 s) before judging.
- Cost: ~17–41k tokens a case, 12–40 s of mind time; nearly all of it the
  first-look dump and the tool kit on every turn.
