# Findings

What the simulator has taught about driving each mind. Newest first. A row is
one run; the record is under `runs/<scenario>/<mind>/cases/`.

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
