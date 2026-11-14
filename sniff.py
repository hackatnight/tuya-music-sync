"""Log every setting change the strips report, to learn how the Smart Life
app drives segments (painting / chase). Run it, use the app, then Ctrl+C.

    python sniff.py
"""
import base64
import json
import threading
import time
from pathlib import Path

import tinytuya

HERE = Path(__file__).resolve().parent
LOG = HERE / "sniff_log.jsonl"


def describe(v):
    """Show raw/base64 DP values as hex too, so the byte layout is visible."""
    if isinstance(v, str) and len(v) > 12:
        try:
            raw = base64.b64decode(v, validate=True)
            return f"{v}  (hex {raw.hex(' ')})"
        except Exception:
            pass
    return repr(v)


def watch(cfg):
    d = tinytuya.Device(cfg["id"], cfg["ip"], cfg["key"], version=3.3)
    d.set_socketPersistent(True)
    d.set_socketTimeout(5)
    last = {}
    first = d.status()
    print(f"[{cfg['name']}] start: {first}", flush=True)
    last.update((first or {}).get("dps", {}))
    beat = time.time()
    while True:
        msg = d.receive()
        if msg and "dps" in msg:
            for k, v in msg["dps"].items():
                if last.get(k) != v:
                    print(f"[{cfg['name']}] DP {k} = {describe(v)}", flush=True)
                    with LOG.open("a") as f:
                        f.write(json.dumps({"t": time.time(), "dev": cfg["name"], "dp": k, "v": v}) + "\n")
                    last[k] = v
        if time.time() - beat > 9:
            d.heartbeat(nowait=True)
            beat = time.time()


for cfg in json.loads((HERE / "devices.json").read_text()):
    threading.Thread(target=watch, args=(cfg,), daemon=True).start()
print("Listening - use the Smart Life app now (Ctrl+C to stop)", flush=True)
while True:
    time.sleep(1)
