"""Tuya music-sync bridge.

Serves the web UI and relays colour frames from the browser to Tuya LED
strips over the LAN (tinytuya, protocol 3.3, music-mode DP).

    python server.py            # real devices from devices.json
    python server.py --demo     # no devices, UI preview only

PC:    http://localhost:8080
Phone: https://<pc-ip>:8443   (accept the self-signed certificate once;
       browsers only allow the microphone on https)
"""
import argparse
import asyncio
import base64
import datetime
import ipaddress
import json
import socket
import ssl
import threading
import time
from pathlib import Path

from aiohttp import web, WSMsgType

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
CERT, KEY = HERE / "cert.pem", HERE / "key.pem"


# ---------------------------------------------------------------- devices

class Strip:
    """One LED strip, driven from its own thread so a slow device never
    stalls the others. Only the newest frame is ever sent; stale frames are
    dropped, which keeps latency low."""

    def __init__(self, cfg, min_interval):
        self.name = cfg.get("name") or cfg["id"]
        self.cfg = cfg
        self.min_interval = min_interval
        self.frame = None
        self.cmd = None
        self.event = threading.Event()
        self.status = "connecting"
        self.dev = None
        self.mode = None
        self.log = False
        threading.Thread(target=self._run, daemon=True).start()

    def push(self, frame):
        self.frame = frame
        self.event.set()

    def command(self, cmd):
        self.cmd = cmd
        self.event.set()

    def _connect(self):
        import tinytuya
        d = tinytuya.BulbDevice(self.cfg["id"], self.cfg["ip"], self.cfg["key"],
                                version=float(self.cfg.get("version", 3.3)))
        d.set_socketPersistent(True)
        d.set_socketTimeout(2)
        d.status()  # detects DP layout (type A/B) and checks the key
        d.turn_on()
        # colour mode, never "music": in music mode these strips run their own
        # built-in-mic effect, which fights our colours and looks erratic
        d.set_mode("colour")
        self.mode = "colour"
        self.dev = d
        self.status = "ok"

    def _send_paint(self, frame):
        """DP 51: per-segment colours plus the strip's own animations.
        Layout worked out from what the Smart Life app sends (base64):
          01 c9 | anim | speed speed | flags | 00 00 | brightness | (hue_hi hue_lo sat) x N
        anim: 00 static, 0a stream, others the app's built-in effects;
        flags: c0 static, e0 animated, +0x10 reverses direction;
        brightness 1-100 for the whole strip; hue 0-359, sat 0-100 per colour.
        Static spreads the colours over the 15 segments; stream runs them
        along the strip with the rest dark."""
        anim = int(frame.get("anim", 0))
        speed = max(1, min(100, int(frame.get("speed", 50))))
        flags = 0xc0 if anim == 0 else (0xf0 if frame.get("reverse") else 0xe0)
        bright = max(1, min(100, int(frame.get("bright", 100))))
        head = bytes([0x01, 0xc9, anim, speed, speed, flags, 0, 0, bright])
        body = b"".join(bytes([int(h) % 360 >> 8, int(h) % 360 & 0xff, max(0, min(100, int(s)))])
                        for h, s in frame["colours"])
        if self.mode != "scene":
            self.dev.set_mode("scene")
            self.mode = "scene"
        self.dev.set_value(51, base64.b64encode(head + body).decode(), nowait=True)

    def _send_colour(self, frame):
        """dp 28 / 27: music-mode colour (28 is what the Smart Life app uses
        while dragging the colour wheel, 27 is its music-mode channel);
        dp 24: plain colour mode. Strips differ in which reacts fastest."""
        d = self.dev
        r, g, b = frame["rgb"]
        dp = int(frame.get("dp", 24))
        hexv = d.rgb_to_hexvalue(r, g, b, d.dpset["value_hexformat"])
        want = "colour" if dp == 24 else "music"
        if self.mode != want:
            d.set_mode(want)
            self.mode = want
        if dp == 24:
            d.set_value(24, hexv, nowait=True)
        else:
            transition = 0 if frame.get("jump", True) else 1
            d.set_value(dp, "%x" % transition + hexv + "00000000", nowait=True)

    def _run(self):
        last = 0.0
        while True:
            self.event.wait(1.0)
            self.event.clear()
            try:
                if self.dev is None:
                    self._connect()
                cmd, self.cmd = self.cmd, None
                if cmd == "on":
                    self.dev.turn_on()
                elif cmd == "off":
                    self.dev.turn_off()
                elif cmd == "white":  # colour-only strips: white = full RGB
                    self.dev.turn_on()
                    self._send_colour({"rgb": (255, 255, 255), "dp": 24})
                frame, self.frame = self.frame, None
                if frame:
                    # the page sends sparse beat events (flash, then fade), so
                    # each one is sent rather than replaced by the next
                    wait = self.min_interval - (time.monotonic() - last)
                    if wait > 0:
                        time.sleep(wait)
                    if "colours" in frame:
                        self._send_paint(frame)
                    else:
                        self._send_colour(frame)
                    last = time.monotonic()
                    if self.log:
                        print(f"{self.name}: sent {(time.time() - frame.get('t', time.time() * 1000) / 1000) * 1000:.0f} ms after page")
            except Exception as e:  # device dropped off: retry after a pause
                self.status = f"error: {e}"
                self.dev = None
                time.sleep(2)


def load_devices():
    """devices.json comes from `python -m tinytuya wizard`; IPs come from it,
    from snapshot.json (written by `tinytuya scan`), or from a LAN scan."""
    path = HERE / "devices.json"
    if not path.exists():
        raise SystemExit("devices.json not found - run `python -m tinytuya wizard` "
                         "in this folder first (or use --demo).")
    devices = json.loads(path.read_text())
    ips = {}
    snap = HERE / "snapshot.json"
    if snap.exists():
        for d in json.loads(snap.read_text()).get("devices", []):
            if d.get("ip"):
                ips[d["id"]] = d["ip"]
    out = []
    for d in devices:
        if not d.get("key"):
            continue
        ip = d.get("ip") or ips.get(d["id"])
        if not ip:
            import tinytuya
            found = tinytuya.find_device(d["id"])
            ip = found.get("ip")
        if ip:
            out.append({**d, "ip": ip})
        else:
            print(f"! {d.get('name', d['id'])}: not found on the LAN, skipped")
    return out


# ---------------------------------------------------------------- web

async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    strips = request.app["strips"]
    await ws.send_json({"type": "devices",
                        "devices": [{"name": s.name, "status": s.status} for s in strips]})
    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            continue
        data = json.loads(msg.data)
        targets = [s for i, s in enumerate(strips)
                   if data.get("targets") is None or i in data["targets"]]
        if data["type"] == "frame":
            for s in targets:
                s.push(data)
        elif data["type"] == "cmd":
            for s in targets:
                s.command(data["cmd"])
        elif data["type"] == "status":
            await ws.send_json({"type": "devices",
                                "devices": [{"name": s.name, "status": s.status} for s in strips]})
    return ws


async def index(request):
    return web.FileResponse(STATIC / "index.html")


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert(ip):
    if CERT.exists() and KEY.exists():
        return
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "tuya-music-sync")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address(ip)),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="run without devices")
    ap.add_argument("--rate", type=float, default=12,
                    help="max updates per second per strip (default 12)")
    ap.add_argument("--log", action="store_true", help="print timing for every command")
    args = ap.parse_args()

    strips = [] if args.demo else [Strip(c, 1 / args.rate) for c in load_devices()]
    for s in strips:
        s.log = args.log
    app = web.Application()
    app["strips"] = strips
    app.add_routes([web.get("/", index), web.get("/ws", ws_handler),
                    web.static("/static", STATIC)])
    runner = web.AppRunner(app)
    await runner.setup()

    ip = lan_ip()
    ensure_cert(ip)
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(CERT, KEY)
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    await web.TCPSite(runner, "0.0.0.0", 8443, ssl_context=ctx).start()

    print(f"Strips: {', '.join(s.name for s in strips) or '(demo mode)'}")
    print(f"PC:    http://localhost:8080")
    print(f"Phone: https://{ip}:8443  (accept the certificate warning once)")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
