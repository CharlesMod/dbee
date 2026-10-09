# sick

A frame is sick when jobs keep lapsing on it: the court took back their leases because the frame stopped answering while it held them (hive/court/reaper.go), and each lapse counts against the frame. Every job the frame carries to an end forgives one, so the court reads it `quarantined` only while lapses outrun finished work. The doctor triages it, holds it while it is mended, and returns it to the fleet's work.

## Routes, files, units
- GET /v1/drones: the frame's `reliability` (trusted, flaky, quarantined) and its `held` (case, why, at), when held
- POST /v1/drones/{frame}/hold {case, why}: the fleet's work goes round the frame; only work addressed to it by name (node:<frame>) lands there, so probes and fixes still reach it; frame_held on the spine
- POST /v1/drones/{frame}/return {case, why}: back to the fleet's work, its lapse record wiped; frame_returned on the spine with the old count
- the spine's abscond events on the frame: which jobs it lost and when

## Invariants
- a hold and a return name their case and why, and land on the spine
- a held frame still takes work addressed to it by name: the doctor's probes and fixes, the keeper's `hive run FRAME`
- a frame is returned only once the case judged it mended (a probe on it reads green); a closed case leaves no hold behind

## Known fault shapes
- one-bad-night: the lapses came together (a reboot, a sleep, an update) and the frame is live and finishing work since. Confirm: lapses (the absconds are clustered), then downtime on the frame. Fix: return it with that why; no hold is needed.
- starved: the frame runs out of memory or disk under load and its drone stops answering mid-job. Confirm: lapses, then disk and units on the frame. Fix: hold, the runbook's fix (prune, a lighter pin), then return once the frame's probe reads green.
- flapping-link: the frame drops off the tailnet again and again while working. Confirm: lapses, then downtime (network drops in its log). Fix: hold, consult if the cause is a router or cable a person must touch, return once it holds a link.
- stale-hold: a hold no open case owns (its case closed or was lost). Confirm: lapses (held, by a case that is closed). Fix: return it, saying the case is gone.
