#!/bin/sh
# The ray probe: does this frame's Ray stand where the court says the head is?
# Exit 1 (red): the court orders a ray role here and no Ray of that role runs, or
# a worker runs joined to an address that is not the live head's (a head that
# moved, or one on a silent frame). Exit 0: no ray order here, or the role runs
# where it should. Read only: it changes nothing. Verdict first, then the facts.
exec python3 - <<'EOF'
import json, os, socket, subprocess, urllib.request

court = (os.environ.get("HIVE_COURT") or "").rstrip("/")
node = os.environ.get("HIVE_NODE") or socket.gethostname()
facts = []


def get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except Exception as e:  # noqa: BLE001 - a probe reports, never raises
        facts.append(f"the court did not answer {url}: {e}")
        return None


drones = (get(f"{court}/v1/drones") or {}).get("drones") or [] if court else []
mine = next((d for d in drones if d.get("node") == node), {})
order = next((c.split(":", 1)[1] for c in (mine.get("config") or {}).get("caps_extra") or ()
              if c.startswith("ray:")), "")
heads = [(d.get("node"), d.get("addr"), d.get("live") is not False) for d in drones
         if "ray:head" in ((d.get("config") or {}).get("caps_extra") or ())]
live_heads = [h for h in heads if h[2]]
facts.append("the court's ray order for this frame: " + (order or "none"))
facts.append("the frames the court orders head: " + (", ".join(
    f"{n} at {a} ({'live' if l else 'SILENT'})" for n, a, l in heads) or "none"))

# the frame's processes (a test hands them in, so it never reads its own host's Ray)
ps = os.environ["HIVE_PROBE_PS"] if "HIVE_PROBE_PS" in os.environ else \
    subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
runs = [l.strip() for l in ps.splitlines() if ("ray.scripts.scripts start" in l or " ray start" in l)
        and "python3 -" not in l and "sh -c" not in l]   # a Ray, not this probe's own text
joined = sorted({a.split("=", 1)[1].rsplit(":", 1)[0] for l in runs for a in l.split()
                 if a.startswith("--address=")})
is_head = any("--head" in l.split() for l in runs)
facts.append("Ray running here: " + ("; ".join(r[:160] for r in runs) or "none"))

red = ""
if order == "worker":
    if not runs:
        red = "the court orders a worker here and no Ray runs"
    elif not live_heads:
        red = "a worker runs here but the court orders no live head anywhere"
    elif not set(joined) & {a for _n, a, _l in live_heads}:
        red = (f"the worker here joined {', '.join(joined) or 'no address'}, not the live head "
               f"{live_heads[0][0]} at {live_heads[0][1]}")
elif order == "head" and not is_head:
    red = "the court orders the head here and no Ray head runs"

print(("RED: " + red) if red else f"GREEN: {'no ray order here' if not order else 'its ray ' + order + ' runs where the court says'}")
print("\n".join(facts))
raise SystemExit(1 if red else 0)
EOF
