#!/bin/sh
# The engine probe: does the pin this frame serves, or is said to serve, answer on its port?
# Exit 1 (red): a pin is applied here, or the court advertises one for this frame, and nothing
# answers on its port. Exit 0: the engine answers, or the frame serves nothing and says so.
# Read only: it changes nothing. It prints the verdict first, then the facts it rests on.
exec python3 - <<'EOF'
import json, os, socket, subprocess, time, urllib.request

home = os.environ.get("HIVE_HOME") or os.path.expanduser("~/.hive")
court = (os.environ.get("HIVE_COURT") or "").rstrip("/")
node = os.environ.get("HIVE_NODE") or socket.gethostname()
facts = []


def read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:  # noqa: BLE001 - a probe reports, never raises
        return 0, str(e).encode()


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return ""


# the applied pin, as the drone says it (`drone pin show`: the record is the
# drone's, and the pid it keeps is read only by the drone's proof)
drone = os.environ.get("HIVE_DRONE") or os.path.join(home, "bin", "drone")
try:
    shown = json.loads(sh(f"'{drone}' pin show") or "{}")
except ValueError:
    shown = {}
pin = shown if shown.get("applied") else None
role = read_json(os.path.join(home, "rolehold.json"))
facts.append("applied pin: " + (f"{pin.get('model')}@{pin.get('pin_fp')} on :{pin.get('port')}"
                                f" ({pin.get('slots')} slots), its engine "
                                + ("provably alive" if pin.get("engine_alive") else "not proven alive")
                                if pin else "none")
             + ("; a record is set aside" if shown.get("aside") else ""))
facts.append("role held: " + (f"job {role.get('id')} serving {(role.get('needs') or {}).get('model')}"
                              if role else "none"))

advert, order = [], None
if court:
    code, body = get(f"{court}/v1/drones")
    try:
        rows = json.loads(body).get("drones") or []
    except (ValueError, AttributeError):
        rows = []
    me = next((d for d in rows if str(d.get("node", "")).lower() == node.lower()), None)
    if me is not None:
        node = me.get("node") or node
        caps = me.get("caps") or me.get("capabilities") or []
        advert = [c for c in caps if str(c).startswith(("llm:serve:", "llm:endpoint:"))]
    code, body = get(f"{court}/v1/drones/{node}/config")
    try:
        order = (json.loads(body) or {}).get("serve") if code == 200 else None
    except ValueError:
        order = None
facts.append("the court advertises for this frame: " + (", ".join(advert) or "nothing served"))
facts.append("the court's serve order for this frame: "
             + (f"{order.get('model')}@{order.get('pin_fp', '')}" if isinstance(order, dict)
                else "none (a role, if held, is the order)"))

port = (pin or {}).get("port") or next((int(c.split(":")[-1]) for c in advert
                                         if c.startswith("llm:endpoint:")), 4411)
listen = [l.split()[3] for l in sh(f"ss -ltnH 'sport = :{port}'").splitlines() if l.split()]
answer = ""
if listen:
    addr = listen[0].replace("0.0.0.0", "127.0.0.1").replace("*", "127.0.0.1")
    code, _ = get(f"http://{addr}/health", timeout=4)
    answer = f"GET http://{addr}/health -> {code or 'no answer'}"
    up = code == 200
else:
    up = False
facts.append(f"listening on :{port}: " + (", ".join(listen) or "nothing") + (f"; {answer}" if answer else ""))
engines = [l.strip() for l in sh("ps -eo pid,stat,etime,args | grep '[l]lama-server'").splitlines()]
facts.append("engine processes: " + ("; ".join(e[:90] for e in engines[:3]) or "none"))

log = sh("{ journalctl -u hive-drone --since -3h --no-pager -o cat; "
         "journalctl --user -u hive-drone --since -3h --no-pager -o cat; } 2>/dev/null")
said = [l for l in log.splitlines() if "drone: " in l and "material" not in l
        and "melissa." not in l and any(k in l for k in (
            "pin ", "pin;", "engine", "role ", "serving", "served", "advertising the",
            "no longer advertising", "restored", "reaped"))]
facts.append("the drone's last words on its engine:")
facts += ["  " + l.split("drone: ", 1)[1][:160] for l in said[-10:]] or ["  (none in 3 h)"]

said_serving = bool(pin) or bool(advert)
if said_serving and not up:
    print(f"RED: this frame is said to serve (applied pin: {'yes' if pin else 'no'}, "
          f"advertised: {'yes' if advert else 'no'}) but nothing answers on :{port}")
    code = 1
elif up:
    print(f"GREEN: the engine answers on :{port}")
    code = 0
else:
    print("GREEN: this frame serves nothing and says it serves nothing")
    code = 0
print("\n".join(facts))
raise SystemExit(code)
EOF
