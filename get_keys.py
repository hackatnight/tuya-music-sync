"""Get local keys straight from your Smart Life account (no Tuya developer
project needed), using the same QR login as Home Assistant's Tuya integration.

    python get_keys.py <user code>

User code: Smart Life app -> Me -> Settings (gear) -> Account and Security
-> User Code. Scan the QR code that opens with the Smart Life app
(Me -> scan icon, top right) and confirm. Writes devices.json.
"""
import json
import os
import sys
import time
from pathlib import Path

import qrcode
from tuya_sharing import LoginControl, Manager

HERE = Path(__file__).resolve().parent
CLIENT_ID = "HA_3y9q4ak7g4ephrvke"   # Home Assistant's public Smart Life client
SCHEMA = "haauthorize"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    user_code = sys.argv[1].strip()
    login = LoginControl()

    r = login.qr_code(CLIENT_ID, SCHEMA, user_code)
    if not r.get("success"):
        raise SystemExit(f"Could not start login: {r.get('msg', r)}  (check the user code)")
    token = r["result"]["qrcode"]

    png = HERE / "login_qr.png"
    qrcode.make(f"tuyaSmart--qrLogin?token={token}").save(png)
    os.startfile(png)
    print("Scan the QR code that just opened with the Smart Life app (Me -> scan icon), then confirm.")

    for _ in range(100):  # about 5 minutes
        time.sleep(3)
        ok, info = login.login_result(token, CLIENT_ID, user_code)
        if ok:
            break
    else:
        raise SystemExit("Timed out waiting for the scan - run it again.")
    png.unlink(missing_ok=True)

    mgr = Manager(CLIENT_ID, user_code, info["terminal_id"], info["endpoint"], {
        "t": info["t"], "uid": info["uid"], "expire_time": info["expire_time"],
        "access_token": info["access_token"], "refresh_token": info["refresh_token"]})
    mgr.update_device_cache()

    devices = []
    for d in mgr.device_map.values():
        devices.append({"name": d.name, "id": d.id, "key": d.local_key,
                        "product_name": d.product_name, "product_id": d.product_id,
                        "category": d.category, "model": getattr(d, "model", ""),
                        "version": "3.3"})
        print(f"  {d.name}: {d.product_name} ({d.category}), id {d.id}")
    (HERE / "devices.json").write_text(json.dumps(devices, indent=2))
    print(f"Saved {len(devices)} device(s) to devices.json")


if __name__ == "__main__":
    main()
