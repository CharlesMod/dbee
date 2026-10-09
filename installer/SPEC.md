# DBee Setup (spec)

A Go program, `dbee-setup`, built on Wasp (`github.com/CharlesMod/wasp`: its
`wizard`, `profile`, `fit`, `catalog`, `fetch`, `engine`, `service`, `runtime`
packages). It lives in this directory as its own Go module
(`github.com/CharlesMod/dbee/installer`, Go 1.23, `CGO_ENABLED=0`), so DBee's
Python stays as it is. One binary per platform: `DBee Setup.exe` (Windows),
`dbee-setup` for macOS (arm64) and Linux (amd64, arm64).

DBee and the Hive work together and neither requires the other: Setup reuses
an engine or a model the Hive already put on the machine (found by sha256), and
offers the Hive's router as the mind when a Hive is here; it never needs one.

## The pages (Wasp wizard, accent: the Hive palette's `medic` blue #38a8ff)

1. **Welcome**: what DBee is in three lines; the banner (`assets/banner-*.png`).
2. **This machine**: the Wasp profile in plain words: OS, CPU, RAM (total,
   free), each GPU and its VRAM (or "none found": runs on the CPU), free disk
   at the install root. A Hive here is said too (a drone or `hive` on PATH, or
   `~/.hive/`).
3. **Choose a mind**: one card per model in DBee's catalog
   (`installer/catalog.json`: qwen3.5-4b-iq4xs, gemma-4-26b-a4b-iq3s,
   swift-qwen3.8-27b-iq3xs, with the facts and sha256 of Wasp's
   `examples/catalog.json`), each from `fit.Recommend` on this profile:
   - **Recommended** (one, marked), then the others that fit, each saying its
     shape in words ("all on the graphics card: fast", "experts in system
     RAM: good", "on the processor: slow"), the context it gets, the download
     size, and "already on this machine" when Find matches its sha256.
   - **Locked** cards greyed and unselectable, with the fit's reason ("needs
     13.6 GB on the card; this one has 8.0").
   - Three other ways, below: "A model I already serve" (a URL, tested with
     one call before Next is allowed), "Claude" (an API key, kept in
     `~/.config/dbee/secrets.env`, mode 600, never shown again), and, when a
     Hive is here, "This Hive's minds" (its court URL).
4. **What to watch**: the services found on this machine (Linux `systemctl
   list-units --type=service --all`, macOS `launchctl list` plus
   `/Library/LaunchDaemons` labels, Windows `Get-Service`), failed and running
   first, a filter box; check any number; or "the whole machine". A health
   URL field (optional).
5. **Ready**: what will be installed where, in a list (Python, DBee, engine,
   model, services, the config), the disk it takes, the install root
   (default: Linux `~/.local/share/dbee`, macOS `~/Library/Application
   Support/DBee`, Windows `%LOCALAPPDATA%\DBee`).
6. **Installing**: the Wasp step runner.
7. **Done**: DBee is watching N services with mind M; how to see its cases
   (`dbee cases`, the folder), how to stop or uninstall.

## The stages (`Plan` from the answers)

1. **Python**: `runtime.Python` into `<root>/python` (skipped when a usable
   one is already there).
2. **DBee**: the DBee package (the `dbee/` directory and its assets, embedded
   in the binary at build time with `go:embed` from a staged copy; a
   `-dbee-src DIR` flag overrides for development) into `<root>/app`; a
   launcher `<root>/bin/dbee` (`dbee.cmd` on Windows) that runs it with the
   private Python.
3. **Engine** (local model only): `engine.Find` (the Hive's and Wasp's roots)
   or `engine.Install` into `<root>/engine`.
4. **Model** (local model only): `fetch.Find` by sha256 in the Hive's
   `~/.hive/models` and Wasp's models root, else `fetch` it into
   `<root>/models` with progress; verified.
5. **Config**: `<root>/dbee.toml` (the mind spec: for the local model
   `openai:http://127.0.0.1:<port>/v1#<name>`, the effort for thinking
   models, the watches, `[doctor] home`).
6. **Services**: `dbee-mind` (llama-server with `engine.ServeArgs` for the
   chosen shape, ctx and slots, on 127.0.0.1 and a free port, restart on
   failure), then `dbee` (`<root>/bin/dbee watch --config <root>/dbee.toml`,
   restart on failure, its log in `<root>/logs`).
7. **Check**: wait for the mind's `/health` (a bounded wait: the one honest
   timer, on a server still loading), make one tiny chat call through
   `dbee`'s own mind code, and read the service's status. A failure here
   says what failed and leaves everything installed so Retry can resume.

Non-interactive: `dbee-setup --yes [--model NAME | --mind-url URL |
--claude] [--watch svc,svc | --whole-machine] [--root DIR]` runs the same
stages with the recommended choices filled in, for a person on ssh and for CI.

Uninstall: `dbee-setup --uninstall` stops and removes the two services and
`<root>` (the models a Hive also uses are never removed).

## Tests
- Pages: drive the wizard over HTTP with `--no-window` and a fake profile
  (`WASP_PROFILE_JSON`): a 4 GB laptop sees the 26B recommended with experts in
  RAM and the 27B locked; a no-GPU 8 GB box sees only the 4B, on the CPU.
- Stages: with fake downloads (httptest) and a fake service runner, a full
  install into a temp root writes the config, the launcher and the two
  service definitions; a second run reuses everything (no download).
- Never touch the real machine's services in tests.
