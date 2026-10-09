# engines

A frame serves a model through one engine (llama-server), started and kept by its drone (swarm/drone).
The engine binds the frame's tailnet address on :4411, never loopback: a 127.0.0.1 probe reads it as dead.
What a frame serves is one order: the court's serve config for it (`hive serve`, a hand's or the keeper's), else the role it holds.
A role is a court job of class llm.role the placer posts for a need (`hive needs`); the drone holds its lease and serves its pin.
The router (`hive think --seats`) lists a frame only while its engine serves; a frame that serves nothing is not a fault.

## Routes, files, units
- the applied pin, as the drone says it: `drone pin show` (model, pin_fp, port, slots, whether its engine is provably alive; the record and its pid are the drone's); ~/.hive/rolehold.json: the held role's lease
- GET /v1/drones/{node}/config: the court's serve order (`serve`); the placer's posts and cancels are spine events (placer_posted, placer_cancelled, pin_served, pin_released)
- the drone's poll every 2 s: no order and no record is none; an order and no record is apply; a record and no order is release; both and the port backing it is keep
- apply: fetch the weights, start the engine, fit it to the card, probe it, then advertise llm:serve:<model>@<fp>, llm:endpoint:4411, llm:slots:<n>
- a drone updates itself by exec and keeps its pid; a role held before is restored at boot ("role ... restored after a restart") and its engine kept
- the drone log: journalctl -u hive-drone (a root install) or --user -u hive-drone

## Invariants
- a frame advertises llm:serve only while its engine answers on its port
- an applied pin record stands for an engine that is alive
- the placer orders only frames that stand on nothing or on its own orders; a hand's serve order is never changed by it

## Known fault shapes
- engine-dead-under-pin: a pin is applied (or advertised) and nothing answers on its port. Confirm: probe engine (exit 1, "RED: this frame is said to serve"). Fix: runbook reapply-pin (sets the record aside; the drone applies its order again), verified by probe engine.
- released: the placer let the frame's role go ("no need wants it now"), the drone released its pin and stopped advertising, and the router dropped the frame. Confirm: probe engine (exit 0, "serves nothing and says it serves nothing") and probe placer (exit 0, its last word a cancel). Not a fault: close it. Whether the frame should serve is the keeper's: a need (`hive needs`) or a serve order.
- loading: pin_served not yet on the spine and the drone's last words say it is fetching or loading. Confirm: probe engine again after a minute. Fix: none; it lands by itself.
- refused: the drone refused the order (pin_refused, "pin-refused" in its status). Confirm: probe engine (its last words). Fix: consult; a refusal is the hardware's or the registry's word.
