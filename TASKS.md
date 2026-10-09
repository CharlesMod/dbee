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
- [x] Fast sim: each scenario declares `recur_s`; seeds trigger their fault now instead of waiting on a clock; `--repeat N` for pass rates; all scenarios at once (2026-10-09: the last clock, a sleep for journalctl to attach, replaced by reading from the patient's clock as arming began; validated 8/10 with oom-service held; disk-full-root missed its wake once in the full sweep and passed alone twice: a flake to watch)
- [ ] The 4B, massively parallel, `--repeat 3`: a pass rate per scenario
- [ ] Lift the oom-service hold once the Hive's drone counts only its own engine's OOM kills (the Hive's fix, in flight elsewhere)

---

## M1: Abstract (any OS, any service)

**Patients: reaching a machine**
- [x] Linux: local, ssh, podman (2026-10-09)
- [x] macOS: local, ssh, and a Hive frame by `hive run` (2026-10-09; live on a macOS 26.5 frame: detected, `com.hive.drone` resolved to its user domain and read running)
- [x] Windows: local PowerShell, OpenSSH-to-PowerShell and a WSL frame's Windows side by `hive run` (one layer: `-EncodedCommand`, progress silenced, text out) (2026-10-09; live on Windows 11 Pro / PowerShell 5.1: Tailscale resolved through the SCM, state, ports, events read)
- [x] A patient says what it is once (`patient.platform`, `dbee platform`): linux/systemd, macos/launchd, windows/scm (2026-10-09)

**Watchers: what wakes it (events, never a poll except the honest health watchdog)**
- [x] journald follow: unit failed, OOM kill, a line matching a pattern (2026-10-09)
- [x] macOS: `log stream --style ndjson` (errors, faults, launchd's abnormal exits); pinned by recorded lines (2026-10-09) — a live stream on the Mac is next (a Hive frame cannot be streamed through jobs)
- [x] Windows: an `EventLogWatcher` subscription (event-driven, no poll): SCM 7031/7034/7023/7024/7000/7009 and critical/error events naming the service; pinned by recorded events (2026-10-09) — a live stream is next
- [x] Plain log file tail for anything else (follow by name across rotation) (2026-10-09: `[[watch]] file`, `dbee watch --file`; from the end as DBee began, nothing missed while the follower opens; Windows follows appends but not yet a rename-rotation)
- [x] Debounce and fold: one case per fault, a storm of lines is one wake (2026-10-09: a wake raised before its subject's last case ended is that case's; one after is a recurrence; keyed on the case's end, not a five-minute window)

**Point it at a service** (`dbee watch SERVICE` resolves the service per platform and watches its stream with the platform's critical-line default, `--pattern` to override: built 2026-10-09, live run on macOS and Windows next)
- [x] `dbee watch SERVICE`: works out the service's log source and manager on its own (systemd unit / launchd label / Windows service name), with the critical-line patterns defaulted per platform (`crit|emerg|fatal|panic|segfault|Traceback|OOM|failed`) and overridable
- [x] `dbee.toml`: services, patterns, the mind, its court, budgets, the case's 3 h bound; one file (2026-10-09; quiet hours still open)
- [x] Install as a service itself: systemd unit, launchd plist, Windows service (or a scheduled task at boot); survives reboot, runs with the least rights the cures need

**Looks and cures per platform**
- [x] Read-only families for macOS (`log show`, `launchctl print`, `lsof`, `vm_stat`, `diskutil info`, `scutil --dns`, `security find-certificate`) and Windows (a PowerShell checker read by effect: read verbs and aliases, native tools with their write arguments, no call operator, no redirection but `2>$null`, no write methods, no secret stores) (2026-10-09, 61 tests)
- [x] Each platform's NEVER list (Windows: `Format-Volume`, `Remove-Item -Recurse` of system trees, `bcdedit`, registry hive deletes; macOS: `diskutil erase*`, `csrutil`, `rm -rf /System`…)
- [x] Pre-cure backups on every platform (a delete is a move) (2026-10-09: in the patient's user state, portable tools only; PowerShell copies every Windows path a cure names)
- [x] Re-read of what woke it per manager: systemd (oneshot by result), launchd (running, or a clean last exit), Windows SCM (Win32_Service state and exit code) (2026-10-09)

**Minds**
- [x] The Hive's router (any model it serves), Claude, a file seat for a person (2026-10-09)
- [x] Any OpenAI-compatible endpoint (Ollama, LM Studio, llama-server, vLLM) by URL alone; streamed, ended by silence (120 s) not length (2026-10-09)
- [x] Per-phase reasoning effort for thinking models (2026-10-09: llama.cpp's chat_template_kwargs and the top-level reasoning_effort vLLM, Ollama and OpenAI read; Claude's extended thinking waits on the Claude-ceiling row, since thinking with tools must carry its thinking blocks back)

**Reach the human**
- [x] A hand-off goes somewhere a person will see it (2026-10-09: `[notify] url` POSTs the report with a Title, ntfy-style; `[notify] command` gets it on stdin for mail, Telegram or a toast; a failed send is logged, never raised)
- [x] A case report a person can read in a minute (markdown), beside the full transcript (2026-10-09: `cases/<id>.md`, rewritten with the JSON every turn)

**Prove it**
- [ ] Sim patients for macOS and Windows: what can be faithful (a Windows container or VM, a macOS VM), and a plan for the rest. The plan (2026-10-09, from the end-to-end runs):
  - **What is faithful already: a user-domain patient on a real frame.** The e2e runs broke a test LaunchAgent (`com.dbee.e2e.*`, its files in a temp dir) and a test SCM service (`DBeeE2E*`, `cmd /c exit 1`) and DBee woke, read and cured them through the same watchers, looks and cures it uses on a real service. A scenario is `seed.ps1|seed.sh`, `check`, `unseed` that touch only their own label/service and temp dir, reached by `hive run --with` (the Hive's door, never ssh); a refused seed is exit 4 as on Linux.
  - **Ports first**: perms (a config the agent cannot read), a missing binary or a bad path, a port taken by another listener, a full temp volume (a RAM disk on macOS, a VHD on Windows), a stale lock file, a planted instruction in a log. Not ported: anything needing root/admin system-wide (disk-full-root, dns-broken), which waits for a VM.
  - **VMs, later**: macOS on Apple silicon through Virtualization.framework (Tart, an 8 GB guest: the 16 GB MacBook holds one), Windows through Hyper-V or Windows Sandbox on DESKTOP (a clean image per run, admin inside). Both only with the placer session's word for the frame and its RAM.
- [ ] Tier 2: misleading logs, two faults at once, a fault only a human can fix (score the hand-off) — written and validated 2026-10-09 (`scenarios/t2`: misleading-logs, a dangling release symlink under loud unrelated database/OOM errors, whose shortcut (making the missing dir) stays red; two-faults, a port squatter plus an unwritable log dir; token-revoked, a supplier's 401 only the account owner can cure, right end a hand-off, and touching the supplier or the token unsafe); the sim now scores right ends (fixed and closed, or handed where only a person can). Next: a pass rate on the 26B and the 4B once the Hive clears the runs
- [ ] The Claude ceiling on every tier (needs the key in `~/.config/dbee/secrets.env`)

---

## M1b: Standalone DBee (the keeper, 2026-10-09)

DBee must install and run on its own for anyone: a GUI installer, a ride-along
model server, a private Python, recommendations from the machine's RAM and VRAM
with impossible choices locked out. The machinery is **Wasp**
(github.com/CharlesMod/wasp), the installer kit the Hive and DBee share: each
stands alone, each reuses what the other installed (engines and models by
sha256), neither requires the other.

- [x] Wasp: the spec (2026-10-09)
- [x] Wasp phase 1: machine profile (RAM, VRAM per vendor, unified memory, WSL), GGUF facts by HTTP Range, model fit (gpu / moe-offload / partial / cpu) with lockouts and a recommendation, verified resumable downloads, the llama.cpp engine (pinned to the fleet's b11279), `wasp-look`
- [x] Wasp phase 2: the setup wizard kit (the Hive's pages and palette, the long-polled step runner, the window opener)
- [x] DBee Setup on it: Welcome → This machine → Choose a mind (recommended, fitting, locked with the reason; or a URL to a model already served; or Claude by key) → What to watch (services found on the machine) → Installing → Done
- [x] The ride-along model server: llama-server on loopback as a service, sized by the fit (ctx, slots, offload), restarted on failure (DBee watches its own engine too)
- [x] A private Python (python-build-standalone) carrying DBee, nothing touching the system Python
- [x] DBee itself as a service per platform, watching the chosen services
- [x] On a Hive machine: offer the Hive's router as the mind and reuse the Hive's engine and models; the Hive's installer reuses DBee's in turn
- [x] Release builds: `DBee Setup.exe` (Windows), a macOS app/dmg, a Linux AppImage or tarball; signed later (2026-10-09: `installer/release.sh DEST`: the .exe, a DBee Setup.app zipped for arm64 and amd64, Linux tarballs for amd64 and arm64, SHA256SUMS; unsigned, and no GitHub release published yet)
- [ ] Driven end to end on all three (the keeper, 2026-10-09) — `--yes` done on all three 2026-10-09 (macOS: woke, cured, closed; Windows: woke, diagnosed, handed honestly; Linux: woke, the 4B misdiagnosed, its case kept); each uninstall clean, cases kept until `--purge`; the wizard path is next: a full install (the wizard and `--yes`), DBee waking on a real fault, and a clean **uninstall** on Linux, macOS and Windows, each on a frame the Hive's placer session confirms it can spare at the time; DBee's model server must never take a card the Hive is serving from or stop a node mid-job (on a Hive frame, prefer the Hive's own minds or the CPU). Cleared 2026-10-09 with these conditions: Linux in a throwaway systemd container on the 5080 frame, CPU-only, 6 GB cap, never the host (it holds her home seats); macOS on the MacBook (nothing of the placer's there) once the doctor's open case on it rests; Windows on DESKTOP with DBee's mind = the Hive's router, never a local llama-server (its 4 GB card holds her spare under a live check); nowhere: drone configs, `hive serve`, killing or restarting engines or drones, anything under ~/.hive; tell the placer session when uninstalling on DESKTOP
- [ ] Wasp phase 4: the Hive's `swarm/wasp` moves onto the module (a Hive change, gated and deployed there)

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

- [x] Every case on disk after every turn, with each call's kit, reply, reasoning and serving seat; `dbee export` as JSON lines; uninstall keeps the cases (2026-10-09)
- [ ] A dataset from the sim: every case's transcript, its score, its grounded diagnosis, its verified cure (winning cases as targets, refusals as lessons)
- [ ] A small model (the 4B class) trained on it, for the Hive's machines first
- [ ] Measured against the base model on held-out scenarios: pass rate, unsafe acts (must stay 0), tokens
