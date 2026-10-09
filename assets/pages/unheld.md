# unheld

A mind is unheld when it answers off its schema: fenced in a code block, in prose, or naming a verb its card does not offer. A mind whose rung sends the engine the card's schema (dance.rungs.engine_rung, `grammar_json`) samples only what the schema allows, so an answer off it means the rung that carried the call sent none, or the engine it reached does not hold to one. The tick puts `schema_mismatch` on the spine for every such answer (hive/melissa/tick.py, Core._mismatch); the case is about the code path, not the frame.

## Routes, files, units
- GET /v1/events: `schema_mismatch` (bee, rung, model, url, held: whether the rung said grammar_json, reason, the answer's start) and the run's `core_tick` after it
- hive/dance/rungs.py `engine_rung`: the one builder of an engine rung; a rung built anywhere else is the fault
- the bee's store: context/N.json in its case holds the exact messages and the raw answer

## Invariants
- every rung of the hive's own engine comes from engine_rung and says grammar_json
- a mind held to its schema never writes a fence, prose or a verb off its card
- the case closes once the probe reads green: the mind's newest tick answered on its schema

## Known fault shapes
- hand-built-rung: the event says `no grammar`; a rung was built beside engine_rung. Confirm: unheld (held false), read the bee's flight path. Fix: code, folding the builder into engine_rung.
- remote-rung: the url is not the hive's engine (a frontier helper) and it ignores the schema. Confirm: unheld (the url). Fix: code, holding that rung to a tool call or dropping it from the ladder the bee reads.
- engine-without-grammar: the event says `held` and the answer is still off it: the engine build ignores response_format. Confirm: unheld, then engine on the frame. Fix: consult; the engine's build is the bench's to settle.
