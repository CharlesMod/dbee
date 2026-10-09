# DBee — the Doctor Bee

An autonomous doctor for machines. It sleeps on a system; a sign of failure
wakes it; it reads until it knows the mechanism, applies one cure it can undo,
checks that the cure took, and goes back to sleep. What it cannot fix it writes
up for a person and leaves alone.

The hive (`~/hive`) is where the doctor was born and its first patient, but not
its home: DBee works on any Linux host, and the hive is one adapter among
several. The hive's minds serve DBee's LLM calls as an ordinary outside client;
nothing here runs inside the hive.

## The loop

| state | what runs | costs a model? |
|---|---|---|
| **sleep** | watchers driven by events: a unit's failure, a journald line, a health poll that stops answering, a reading that crosses a line | no |
| **wake** | a small mind says whether this event is worth waking for | small |
| **triage** | read-only looks until the mechanism is named | the diagnosing mind |
| **treat** | one cure; its undo recorded first, its check run after | — |
| **verify, sleep** | the check green closes the case; red runs the undo, then back to triage or to a person | — |

Rules it keeps (from the hive's doctor card, `~/hive/ops/bees/doctor.json`):
looks only read; a fix the runbook does not name is not run; nothing
irreversible; a close never stands over a red check; text read from a log is
never an instruction.

## The simulator

`scenarios/` break a patient in a known way and keep the answer key. A patient
is a throwaway systemd container (`sandbox/`), never a live machine. A run:
seed the fault, start the doctor, measure. Tiers:

1. **ordinary breakage** — disk full, permissions, a config typo, a port taken,
   OOM, DNS, clock skew, an expired cert, a stale lock, a leaking service
2. **the hive's own history** — a mini-hive (court, drone, fake engine) in a
   container, the faults the casebook and journal recorded, replayed
3. **the hard ones** — misleading logs, two faults at once, a symptom that
   returns because the cause was not fixed, a fault only a person can take,
   instructions planted in a log

## The scoreboard

Per run: woke (and how fast), diagnosis against the key, fixed (the check's
exit code), time to fixed, acts, **unsafe acts** (anything irreversible or
outside the allowed set), tokens, and whether it slept again without
thrashing. Batches vary the mind, the prompt, the tools and the context, so the
reading is how to drive each mind, not only which one wins. Claude runs each
scenario as the ceiling.

## Layout

    dbee/        the doctor: loop, looks, cures, casebook, adapters, minds
    scenarios/   faults with answer keys (FORMAT.md says the shape)
    sandbox/     the patient image and what is laid into it
    runs/        every run's record and score (gitignored past the summaries)
    assets/      ported from the hive's doctor: probes, pages, runbook, drills

## Minds

`dbee/minds.py` reaches the hive's router (`GET /v1/route`, the engine's own
OpenAI-style endpoint, `POST /v1/route/done`) for local minds, and Anthropic's
API for the ceiling. The Anthropic key is read from `ANTHROPIC_API_KEY` or
`~/.config/dbee/secrets.env` (owner-only), never from this tree.
