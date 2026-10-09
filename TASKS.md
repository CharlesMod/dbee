# DBee: the MVP tasklist

The dream: **point DBee at a service on almost any machine (Linux, macOS,
Windows). When the service emits a critical log line, DBee springs into
action, brings it back, and goes back to sleep.** Then it becomes the Hive's
doctor bee. A finetune comes last.

Order is the keeper's (2026-10-09): **abstract first → specialize for the Hive
→ Doctor Bee hooks → finetune (low priority).** A box is checked only when
it is built, proven (a test or a sim run) and pushed; write `(date, sha or
reading)` beside it. An open item may carry a one-line note of where it
stands.

---

## Now (in flight)

- [x] Tier-1 scenarios, validated with no mind (2026-10-09, f122865)
- [x] Harness, round 1: close check, reopen on recurrence, per-phase effort, `--jobs` (2026-10-09)
- [x] Harness, round 2 (from the doctor's seat): oneshot units judged by result, look chains judged by effect, grounded diagnoses, pre-cure backups, what-changed incl. transient units, unit scripts read, the patient's biasing comment removed (2026-10-09)
- [ ] Fast sim: each scenario declares `recur_s`; seeds trigger their fault now instead of waiting on a clock; `--repeat N` for pass rates; all scenarios at once
- [ ] The 4B, massively parallel, `--repeat 3`: a pass rate per scenario
- [ ] Lift the oom-service hold once the Hive's drone counts only its own engine's OOM kills (the Hive's fix, in flight elsewhere)

---

## M1: Abstract (any OS, any service)

**Patients: reaching a machine**
- [x] Linux: local, ssh, podman (2026-10-09)
- [ ] macOS: local and ssh (zsh/bash; `/bin/sh` is fine)
- [ ] Windows: local PowerShell and OpenSSH-to-PowerShell (`powershell -NoProfile -Command`); one quoting layer, tested
- [ ] A patient says what it is (os, init, log source, shell) once: a capability, not a check repeated in every look

**Watchers: what wakes it (events, never a poll except the honest health watchdog)**
- [x] journald follow: unit failed, OOM kill, a line matching a pattern (2026-10-09)
- [ ] macOS: `log stream --predicate` (process or subsystem, level error/fault); launchd job exit status
- [ ] Windows: Event Log subscription (`Get-WinEvent` / `wevtutil` query by provider and level; Service Control Manager 7031/7034 "service terminated unexpectedly")
- [ ] Plain log file tail for anything else (follow by name across rotation)
- [ ] Debounce and fold: one case per fault, a storm of lines is one wake

**Point it at a service**
- [ ] `dbee watch SERVICE`: works out the service's log source and manager on its own (systemd unit / launchd label / Windows service name), with the critical-line patterns defaulted per platform (`crit|emerg|fatal|panic|segfault|Traceback|OOM|failed`) and overridable
- [ ] `dbee.toml`: services, patterns, the mind, budgets, quiet hours; one file, no env sprawl
- [ ] Install as a service itself: systemd unit, launchd plist, Windows service (or a scheduled task at boot); survives reboot, runs with the least rights the cures need

**Looks and cures per platform**
- [ ] Read-only families for macOS (`log show`, `launchctl print`, `lsof`, `vm_stat`, `diskutil info`, `scutil --dns`, `security find-certificate`) and Windows (`Get-Service`, `Get-WinEvent`, `Get-Process`, `Get-NetTCPConnection`, `Get-Volume`, `Get-ChildItem`, `Get-Content -Tail`, `Test-NetConnection`)
- [ ] Each platform's NEVER list (Windows: `Format-Volume`, `Remove-Item -Recurse` of system trees, `bcdedit`, registry hive deletes; macOS: `diskutil erase*`, `csrutil`, `rm -rf /System`…)
- [ ] Pre-cure backups on every platform (a delete is a move)
- [ ] Re-read of what woke it per manager: systemd (oneshot by result), launchd (last exit status), Windows SCM (Running / Stopped with exit code)

**Minds**
- [x] The Hive's router (any model it serves), Claude, a file seat for a person (2026-10-09)
- [ ] Any OpenAI-compatible endpoint (Ollama, LM Studio, llama-server, vLLM) by URL alone
- [ ] Per-phase reasoning effort for thinking models (2026-10-09 for the Hive; to generalize)

**Reach the human**
- [ ] A hand-off goes somewhere a person will see it: a desktop notification, ntfy/Pushover/Telegram, email; one line of what is wrong, what was tried, the next step
- [ ] A case report a person can read in a minute (markdown), beside the full transcript

**Prove it**
- [ ] Sim patients for macOS and Windows: what can be faithful (a Windows container or VM, a macOS VM), and a plan for the rest
- [ ] Tier 2: misleading logs, two faults at once, a fault only a human can fix (score the hand-off)
- [ ] The Claude ceiling on every tier (needs the key in `~/.config/dbee/secrets.env`)

---

## M2: Specialize for the Hive

- [ ] A Hive patient: frames reached through the Hive's own doors (`hive run`, the court's API), never ssh
- [ ] Hive watchers: the spine (`/v1/events`): node offline, organ refused, pin refused, a quarantine, the court gone silent
- [ ] Hive looks: the court (GET only), `hive journal`, the drone's own logs, the probes in `assets/probes`
- [ ] Hive cures: the runbook (`assets/runbook.jsonl`), reapply-pin, linger, the audio server; a release/hold/return of a sick frame through the court
- [ ] Tier 2 for the Hive: a mini-Hive in a box (court, drone, a fake engine) replaying recorded faults: engine dead under its pin, no-linger, the stdlib shadow, a stale checkout, the court gone silent, a quarantine loop, the brain stranded on a slow card
- [ ] The Hive's casebook and fault records imported as scenarios (a fault the fleet met becomes a test)

## M3: Doctor Bee hooks

- [ ] The Hive's doctor bee runs DBee's loop (`hive/apiary/doctor.py` calls DBee's `Doctor.treat`; one implementation, the Hive's lean law), behind its card (`ops/bees/doctor.json`)
- [ ] Hooks: the Hive calls DBee on a case opened, a probe gone red, a frame lost; DBee reports through the spine (`doctor_*` events) and receipts
- [ ] The doctor's mind is the router's to choose (Swift-27B today; the 4B as a fast first responder, escalating to Swift when it hands off)
- [ ] The Messenger speaks for it: a hand-off reaches the keeper through Rocky
- [ ] The Hive's existing doctor tests stay green; the fold retires the old loop only when DBee reads no worse on the Hive's own drills

## M4: Finetune (low priority)

- [ ] A dataset from the sim: every case's transcript, its score, its grounded diagnosis, its verified cure (winning cases as targets, refusals as lessons)
- [ ] A small model (the 4B class) trained on it, for the Hive's machines first
- [ ] Measured against the base model on held-out scenarios: pass rate, unsafe acts (must stay 0), tokens
