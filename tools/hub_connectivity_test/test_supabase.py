#!/usr/bin/env python3
"""PC-side Supabase check for the hub (read-only, standard library only).

Reads the Supabase URL + anon key from frontend/.env (VITE_SUPABASE_URL,
VITE_SUPABASE_ANON_KEY) - the same key the hub uses - and checks:
  1. the key is a valid JWT, its role and expiry
  2. DNS + HTTPS reachability of the project
  3. a read-only GET on each table the hub touches (readings, instructions,
     hub_status) -> tells you if the key + row-level-security rules work.
It never writes to the database and never prints the key.

    python tools/hub_connectivity_test/test_supabase.py
"""
import base64
import json
import pathlib
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV = ROOT / "frontend" / ".env"
TABLES = ["readings", "instructions", "hub_status"]


def read_env(path: pathlib.Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def jwt_info(token: str):
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return None


def main() -> int:
    ok_all = True
    if not ENV.exists():
        print(f"FAIL  {ENV} not found")
        return 2
    env = read_env(ENV)
    url = env.get("VITE_SUPABASE_URL", "").rstrip("/")
    key = env.get("VITE_SUPABASE_ANON_KEY", "")
    if not url.startswith("https://") or not key:
        print("FAIL  VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY missing or malformed in frontend/.env")
        return 2

    host = urllib.parse.urlparse(url).hostname
    print(f"Project host : {host}")

    # 1. key sanity
    info = jwt_info(key)
    if not info:
        print("FAIL  key is not a readable JWT")
        ok_all = False
    else:
        exp = info.get("exp")
        exp_s = datetime.fromtimestamp(exp, timezone.utc).strftime("%Y-%m-%d") if exp else "none"
        expired = bool(exp) and exp < time.time()
        print(f"{'FAIL' if expired else 'OK  '}  key role={info.get('role')}  expires={exp_s}"
              f"{'  (EXPIRED)' if expired else ''}")
        if info.get("ref") and info["ref"] not in host:
            print(f"WARN  key was issued for project '{info['ref']}' but URL host is '{host}'")
        if expired:
            ok_all = False

    # 2. DNS
    try:
        ip = socket.getaddrinfo(host, 443)[0][4][0]
        print(f"OK    DNS {host} -> {ip}")
    except OSError as e:
        print(f"FAIL  DNS lookup failed: {e}")
        return 1

    # 3. read-only GET per table
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    for t in TABLES:
        req = urllib.request.Request(f"{url}/rest/v1/{t}?select=*&limit=1", headers=headers)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", "replace")
                rows = json.loads(body) if body else []
                note = f"{len(rows)} row(s) returned" if rows else "empty result (no rows, or RLS hides them)"
                print(f"OK    GET {t:13} HTTP {r.status}  {int((time.time()-t0)*1000)} ms  {note}")
        except urllib.error.HTTPError as e:
            hint = {401: "key rejected", 403: "blocked by row-level security",
                    404: "table not found / not exposed"}.get(e.code, "")
            print(f"FAIL  GET {t:13} HTTP {e.code}  {hint}  {e.read().decode('utf-8','replace')[:120]}")
            ok_all = False
        except Exception as e:
            print(f"FAIL  GET {t:13} {type(e).__name__}: {e}")
            ok_all = False

    print("\nRESULT:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
