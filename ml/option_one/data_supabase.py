"""Pull sensor readings from Supabase and turn them into daily theta-proxy series.

Mirrors the frontend's data-quality handling (frontend/src/lib/format.js
readingTime, frontend/src/lib/calibration.js rawToHumidity) so the ML
pipeline and the dashboard agree on what a reading's timestamp and moisture
value actually are -- see docs/model-design for why that consistency matters.

Two real-world messes get cleaned up here, found by auditing the live table:

1. Duplicate packets. ~16% of rows share an identical
   (node_id, raw, temperature, rssi, snr) payload with another row minutes
   apart -- the same physical transmission logged twice (gateway retry /
   ingestion double-insert), not two independent readings that coincidentally
   match on all five fields including a floating-point SNR. Deduped by
   keeping the earliest `received_at` per exact-payload group.

2. Bogus node_id / recorded_at. A handful of rows carry node_id outside the
   5 calibrated field nodes (cross-talk / test packets) and are dropped.
   `recorded_at` is the node's own RTC and can read near-epoch (RTC not yet
   synced) or drift into the future; readingTime() below applies the same
   "trust recorded_at only if plausible and not after received_at" rule the
   frontend uses, falling back to the server's received_at otherwise.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from config import NODE_IDS, MIN_READINGS_PER_DAY

PAGE_SIZE = 1000
MIN_PLAUSIBLE_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
CLOCK_SLACK_SECONDS = 60


class SupabaseError(RuntimeError):
    pass


def load_credentials(env_path: str | None = None) -> tuple[str, str]:
    """Load SUPABASE_URL/SUPABASE_KEY. Falls back to frontend/.env if this
    folder has no .env of its own, since it's the same Supabase project and
    the anon key there already has select-only scope."""
    load_dotenv(env_path)
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if url and key:
        return url.rstrip("/"), key

    fallback = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    if os.path.exists(fallback):
        env = {}
        for line in open(fallback, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
        url = env.get("VITE_SUPABASE_URL", "")
        key = env.get("VITE_SUPABASE_ANON_KEY", "")
        if url and key:
            return url.rstrip("/"), key

    raise SupabaseError(
        "No Supabase credentials found. Copy ml/option_one/.env.example to "
        "ml/option_one/.env and fill it in (same project as frontend/.env)."
    )


def check_access(url: str, key: str, timeout: float = 15.0) -> None:
    """Confirm read access before doing anything else, per the run order requested."""
    session = _session(key)
    for table in ("readings", "sensor_calibration"):
        resp = session.get(
            f"{url}/rest/v1/{table}", params={"select": "*", "limit": 1}, timeout=timeout
        )
        if resp.status_code in (401, 403):
            raise SupabaseError(
                f"Supabase rejected access to `{table}` (HTTP {resp.status_code}). "
                "Check SUPABASE_KEY is a valid anon key with select via RLS."
            )
        if resp.status_code >= 400:
            raise SupabaseError(f"Supabase check failed for `{table}`: HTTP {resp.status_code}: {resp.text[:300]}")


def _session(key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"apikey": key, "Authorization": f"Bearer {key}"})
    return s


def _fetch_all(session: requests.Session, url: str, table: str, params: dict, timeout: float = 30.0) -> list[dict]:
    rows: list[dict] = []
    page = 0
    while True:
        p = dict(params, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
        resp = session.get(f"{url}/rest/v1/{table}", params=p, timeout=timeout)
        if resp.status_code >= 400:
            raise SupabaseError(f"Supabase GET {table} failed: HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        rows.extend(data)
        if len(data) < PAGE_SIZE:
            return rows
        page += 1


def fetch_calibration(url: str, key: str) -> pd.DataFrame:
    session = _session(key)
    rows = _fetch_all(session, url, "sensor_calibration", {"select": "node_id,air,water"})
    df = pd.DataFrame(rows).set_index("node_id").sort_index()
    return df


def fetch_readings(url: str, key: str) -> pd.DataFrame:
    session = _session(key)
    rows = _fetch_all(
        session,
        url,
        "readings",
        {"select": "id,node_id,raw,recorded_at,received_at,rssi,snr,temperature", "order": "id.asc"},
    )
    return pd.DataFrame(rows)


def filter_valid_nodes(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["node_id"].isin(NODE_IDS)].copy()


def dedupe_readings(df: pd.DataFrame) -> pd.DataFrame:
    """Drop exact-payload duplicate packets, keeping the earliest received_at."""
    before = len(df)
    df = df.sort_values("received_at")
    df = df.drop_duplicates(subset=["node_id", "raw", "temperature", "rssi", "snr"], keep="first")
    dropped = before - len(df)
    if dropped:
        print(f"dedupe_readings: dropped {dropped}/{before} duplicate-payload rows ({100*dropped/before:.1f}%)")
    return df


def resolve_timestamp(df: pd.DataFrame) -> pd.Series:
    """Epoch seconds per reading: recorded_at if plausible and not after
    received_at (+ slack), else received_at. Mirrors frontend readingTime()."""
    # .dt.as_unit("s") before .astype("int64") -- pandas' datetime64 default
    # resolution changed between versions (ns historically, us as of pandas
    # 3.x), so casting straight to int64 silently changes units depending on
    # which pandas is installed. Pinning the unit first makes this robust.
    recv = pd.to_datetime(df["received_at"], utc=True).dt.as_unit("s").astype("int64")
    rec = df["recorded_at"].astype(float)
    plausible = (rec >= MIN_PLAUSIBLE_EPOCH) & (rec <= recv + CLOCK_SLACK_SECONDS)
    return pd.Series(np.where(plausible, rec, recv), index=df.index, dtype="int64")


def raw_to_humidity_fraction(raw: pd.Series, node_id: pd.Series, cal: pd.DataFrame) -> pd.Series:
    """(air - raw) / (air - water), clamped [0,1] -- same mapping as
    frontend/src/lib/calibration.js rawToHumidity, but 0-1 instead of 0-100.
    This is a proxy, not physical theta; calibrate.py fits a linear transform
    (cal_a, cal_b) on top of it per node."""
    air = node_id.map(cal["air"])
    water = node_id.map(cal["water"])
    frac = (air - raw) / (air - water)
    return frac.clip(0.0, 1.0)


def load_daily_theta_proxy(url: str, key: str) -> dict[int, pd.Series]:
    """Full pipeline: fetch -> filter -> dedupe -> resolve timestamp -> humidity
    proxy -> daily mean per node. Returns {node_id: pd.Series indexed by date}."""
    cal = fetch_calibration(url, key)
    readings = fetch_readings(url, key)
    readings = filter_valid_nodes(readings)
    readings = dedupe_readings(readings)

    readings["ts"] = resolve_timestamp(readings)
    readings["date"] = pd.to_datetime(readings["ts"], unit="s", utc=True).dt.floor("D")
    readings["humidity_frac"] = raw_to_humidity_fraction(readings["raw"], readings["node_id"], cal)

    out: dict[int, pd.Series] = {}
    for node_id, grp in readings.groupby("node_id"):
        daily = grp.groupby("date").agg(mean=("humidity_frac", "mean"), n=("humidity_frac", "size"))
        daily = daily[daily["n"] >= MIN_READINGS_PER_DAY]
        s = daily["mean"]
        s.index = s.index.tz_localize(None)
        out[int(node_id)] = s.sort_index()
    return out
