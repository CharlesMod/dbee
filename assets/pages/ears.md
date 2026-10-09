# ears

A room is deaf when its station hears speech and the words never come back. The station (hive/melissa/station.py) records the room, finds a saying by its level, and streams it to the veil's hearing session (`POST /api/hear/start`, then `/api/hear/<sid>/chunk`, its events read from `/api/hear/<sid>/events`); the veil hands the audio to the elected ears, and the ears' partial and final transcripts come back as events. The station counts every saying it hears (`heard.sayings`) and logs every event the ears send (`ears_log`), so a room with sayings and no `final` heard sound and got no words.

## Routes, files, units
- the station's `GET /health` (port 4417 on its frame, the directory's `speech.station` row): status, `ears` (the hearing session id), `chunks_sent`, `heard`, `ears_log`, `gate`, `last_heard`, the device
- the veil (`:4414` on the Queen's seat): the hearing sessions; the directory elects the ears and the mouth, never a flag by hand
- `hive turn ROOM "words"` says words into the room's own ear, quietly: the test of a room through its ear

## Invariants
- a saying a room hears comes back as a final transcript, or as the reason it could not
- a station that cannot open a session says so in its status ("no ears: …", "veil not answering"), never "listening"

## Known fault shapes
- lost-on-the-wire: the station is "listening" with a session id, sends chunks, and no event returns; the room beside the veil hears. Confirm: ears on the deaf frame and on the Queen's frame (one green, one red), then organ on the deaf frame. Fix: consult with the session id and the chunk count; the veil's hearing session for a remote station is the suspect.
- no-ears: the station's status says "no ears: …". Confirm: ears (the status). Fix: the ears organ is down or not elected: engines on the frame that should serve it.
- capture-ended: the station's log says "the capture ended (…Input/output error…)" and the room starts again every few minutes. Confirm: mic on the frame. Fix: exit 2 is the audio-server fix; exit 1 is the keeper's (nothing plugged in, a cable, the card, a mute): consult once with the probe's line and rest.
- muted-gate: the gate reads missing or failed and the room has a wake word. Confirm: ears (the gate). Fix: consult; the wake gate's model is the station's.
