#!/usr/bin/env python3
"""Build a flash-ready copy of the hub firmware with your real secrets filled in.

Takes firmware/hub/hub.ino (READ-ONLY - the repo file keeps its "*****"
placeholders and is never modified), replaces the four secret constants from
secrets/hub-wifi.txt, and writes the result to:

    secrets/hub_build/hub/hub.ino          (+ platformio.ini next to it)

secrets/ is git-ignored, so the real credentials never reach the repo.

    python tools/build_hub_with_secrets.py

Then flash it either way:
  Arduino IDE : open secrets/hub_build/hub/hub.ino, board "ESP32 Dev Module",
                libraries "LoRa" (Sandeep Mistry) 0.8.0 and "ArduinoJson" 7.4.3.
  PlatformIO  : cd secrets/hub_build/hub && python -m platformio run -t upload --upload-port COMx
"""
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "firmware" / "hub"
SECRETS = ROOT / "secrets" / "hub-wifi.txt"
OUT_DIR = ROOT / "secrets" / "hub_build" / "hub"
NAMES = ["WIFI_SSID", "WIFI_PASS", "SUPABASE_URL", "SUPABASE_KEY"]


def c_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def load_secrets() -> dict:
    vals = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v
    vals["SUPABASE_URL"] = vals.get("SUPABASE_URL", "").rstrip("/")
    missing = [n for n in NAMES if not vals.get(n)]
    if missing:
        sys.exit(f"Missing in {SECRETS.name}: {', '.join(missing)}")
    return vals


def main() -> int:
    src = SRC_DIR / "hub.ino"
    if not src.exists():
        sys.exit(f"{src} not found")
    if not SECRETS.exists():
        sys.exit(f"{SECRETS} not found")

    secrets = load_secrets()
    text = src.read_bytes().decode("utf-8")   # bytes: keeps CRLF/LF exactly as in the repo

    for name in NAMES:
        pat = re.compile(rf'^(\s*const\s+char\s*\*\s*{name}\s*=\s*)"([^"\r\n]*)"(\s*;)', re.M)
        found = pat.findall(text)
        if len(found) != 1:
            sys.exit(f"Expected exactly one '{name}' constant in hub.ino, found {len(found)}")
        if found[0][1] and set(found[0][1]) != {"*"}:
            print(f"WARNING: hub.ino already contains a non-placeholder {name} - overwriting in the copy only")
        text = pat.sub(lambda m: m.group(1) + c_str(secrets[name]) + m.group(3), text, count=1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "hub.ino").write_bytes(text.encode("utf-8"))
    ini = SRC_DIR / "platformio.ini"
    if ini.exists():
        shutil.copyfile(ini, OUT_DIR / "platformio.ini")

    print(f"Built {OUT_DIR / 'hub.ino'}")
    print("  filled:", ", ".join(NAMES))
    print("  source firmware/hub/hub.ino was NOT modified")
    print("  this folder is git-ignored (under secrets/) - do not copy it anywhere else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
