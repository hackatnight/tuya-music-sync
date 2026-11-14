# Strip Sync

> **🚧 Work in progress.** This is an unfinished hobby project. It works on my own
> strips, but it's rough around the edges, settings and file formats may change, and
> it has only been tested with one model of Tuya RGBIC strip. Expect bugs.

Syncs Tuya Wi-Fi LED strips to music from a web page on your PC or phone, without the
Smart Life app's built-in music mode.

The browser listens to the audio (PC sound or a microphone), detects beats and tempo,
and works out the colours. `server.py` on the PC sends them to the strips over your local
network, not the cloud, so the lag stays low.

## Features

- **Beat detection across 8 frequency bands** (sub-bass to treble), with a retro LED-style
  EQ, a meter for each band, sensitivity sliders and on/off switches.
- **Tempo (BPM) tracking and beat prediction:** once it locks onto a steady beat, it sends
  each flash early to make up for the strips' delay. The **Sync test** calibrates that delay.
- **Whole-strip effects:** beat pulse, drum colours, strobe, ping-pong and colour swap across
  two strips, VU meter, bass breathe, fire, spectrum and colour wave.
- **Segment effects for RGBIC strips:** an EQ bar along the strip (from one end or from the
  centre), a spectrum bar, a beat-driven stream, and the strip's own built-in animations
  driven by the music.
- **Works on PC and phone**, with a layout that adjusts to the screen size.

## Requirements

- Python 3.10+ with `pip install tinytuya aiohttp tuya-device-sharing-sdk "qrcode[pil]"`
- Tuya / Smart Life Wi-Fi LED strips (protocol 3.3) on the same network as the PC
- Chrome or Edge on the PC (for PC sound capture); any modern phone browser for the mic

## One-time setup: get the local keys

You don't need a Tuya developer account.

1. In Smart Life, go to **Me → Settings → Account and Security → User Code** and copy the code.
2. In this folder, run:

       python get_keys.py YOUR_CODE

3. A QR code opens on the PC. In Smart Life, tap **Me → scan icon** (top right), scan it and
   confirm.

The script writes `devices.json`, which holds names, models and local keys. Each strip's IP
address is looked up on the network automatically, or you can add an `"ip"` field yourself.

> **Keep `devices.json` private** (it's in `.gitignore`). Anyone with it can control your
> strips. If you re-pair a strip in the app, its key changes, so run `get_keys.py` again.

## Run

Double-click `start.bat` (or run `python server.py`). Use `--demo` to try it without strips.

- **PC:** http://localhost:8080
  - **PC sound** captures whatever is playing (Spotify, YouTube…). When Chrome or Edge asks,
    share the tab that's playing music and tick **Share tab audio** (lighter on the PC), or
    pick *Entire screen* and tick **Share system audio**.
  - **Microphone** listens to the room.
- **Phone:** open the `https://<pc-ip>:8443` address the server prints, using the same Wi-Fi.
  Accept the certificate warning once (*Advanced → Proceed*): phones only allow the mic on
  https, and the server makes its own certificate on first run.

The PC has to be running `server.py` either way.

## Tips

- **Strip length:** if part of your strip shouldn't light up, set its length in the Smart
  Life app's device settings. The segment effects have a **Visible segments** setting if fewer
  than 15 segments land on your strip.
- **Timing:** run the **Sync test** and adjust **Light latency** until the flashes land on
  the clicks.
- **Sensitivity:** raise the band sliders if hits are missed, lower them if it flickers on
  everything.
- **Bluetooth speaker with the phone mic:** if the music cuts out when the mic starts, turn
  off **Calls / Phone audio** for the speaker in Android's Bluetooth settings.
- **Firewall:** if Windows Firewall asks about Python, allow it on **Private** networks, or
  the phone can't connect.
- **`--rate N`:** maximum updates per second per strip (default 12). Lower it if a strip lags.

## Known issues / to do

- Only tested with one RGBIC strip model. The segment format (DP 51) was worked out by
  watching what the Smart Life app sends, so other models may differ.
- Built-in animation buttons are still labelled "Effect 1–5" until they're identified.
- Tempo can still read wrong on some rhythms (for example, hip-hop with off-beat kicks).
- Some stray small flashes when only hi-hats or synths are playing.

## Files

| File | What it is |
|---|---|
| `server.py` | Web server and strip bridge (tinytuya) |
| `static/index.html` | The whole web app: audio analysis, effects, UI |
| `get_keys.py` | Gets local keys with a Smart Life QR login |
| `sniff.py` | Logs what the Smart Life app sends to the strips, for reverse-engineering |
| `start.bat` | Windows launcher |
