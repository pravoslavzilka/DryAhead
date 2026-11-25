"""Supabase + Open-Meteo data access, with disk caching.

Independent implementation from ml/option_one/data_supabase.py /
data_weather.py -- not imported from them, per the task brief. Re-derives
the same class of data-quality handling (duplicate packets, stray node
IDs, RTC timestamp faults) from a fresh audit of the live tables, and
fixes one real gap found in that audit (see config.py's timestamp-gap
comment and README.md "Data" section).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

from config import (
    BACKLOG_MAX_GAP_SECONDS,
    CACHE_DIR,
    DEDUPE_KEY_COLUMNS,
    MIN_PLAUSIBLE_EPOCH_STR,
    MIN_READINGS_PER_DAY,
    NODE_IDS,
    NON_BACKLOG_MAX_GAP_SECONDS,
)

PAGE_SIZE = 1000
MIN_PLAUSIBLE_EPOCH = datetime.fromisoformat(MIN_PLAUSIBLE_EPOCH_STR).replace(tzinfo=timezone.utc).timestamp()

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARS = (
    "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max,"
    "temperature_2m_min,relative_humidity_2m_mean,wind_speed_10m_max,"
    "shortwave_radiation_sum"
)


class DataError(RuntimeError):
    pass


def _here(*parts: str) -> str:
    return os.path.join(os.path.dirname(__file__), "..", *parts)


def load_credentials() -> tuple[str, str]:
    """SUPABASE_URL/SUPABASE_KEY from ml/option_two/.env if present, else
    fall back to frontend/.env (same project, same read-only anon key)."""
    local_env = _here(".env")
    if os.path.exists(local_env):
        load_dotenv(local_env)
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
        if url and key:
            return url.rstrip("/"), key

    fallback = _here("..", "..", "frontend", ".env")
    if os.path.exists(fallback):
        env: dict[str, str] = {}
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

    raise DataError(
        "No Supabase credentials found. Copy ml/option_two/.env.example to "
        "ml/option_two/.env and fill it in, or ensure frontend/.env exists."
    )


def _session(key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"apikey": key, "Authorization": f"Bearer {key}"})
    return s


def check_access(url: str, key: str, timeout: float = 15.0) -> None:
    session = _session(key)
    for table in ("readings", "sensor_calibration"):
        resp = session.get(f"{url}/rest/v1/{table}", params={"select": "*", "limit": 1}, timeout=timeout)
        if resp.status_code in (401, 403):
            raise DataError(f"Supabase rejected access to `{table}` (HTTP {resp.status_code}).")
        if resp.status_code >= 400:
            raise DataError(f"Supabase check failed for `{table}`: HTTP {resp.status_code}: {resp.text[:300]}")


def _fetch_all(session: requests.Session, url: str, table: str, select: str, timeout: float = 30.0) -> list[dict]:
    rows: list[dict] = []
    page = 0
    while True:
        params = {"select": select, "order": "id.asc" if table == "readings" else "node_id.asc",
                   "limit": PAGE_SIZE, "offset": page * PAGE_SIZE}
        resp = session.get(f"{url}/rest/v1/{table}", params=params, timeout=timeout)
        if resp.status_code >= 400:
            raise DataError(f"Supabase GET {table} failed: HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        rows.extend(data)
        if len(data) < PAGE_SIZE:
            return rows
        page += 1


def fetch_readings_raw(url: str, key: str, cache_path: str | None = None, use_cache: bool = True) -> pd.DataFrame:
    """All raw `readings` rows, unfiltered (includes stray node IDs -- see
    filter_valid_nodes). Cached to disk since the live table only grows."""
    if cache_path is None:
        cache_path = _here(CACHE_DIR, "readings_raw.json")
    if use_cache and os.path.exists(cache_path):
        rows = json.load(open(cache_path, encoding="utf-8"))
    else:
        session = _session(key)
        rows = _fetch_all(session, url, "readings",
                           "id,node_id,raw,temperature,recorded_at,rssi,snr,is_backlog,received_at")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(rows, open(cache_path, "w", encoding="utf-8"))
    return pd.DataFrame(rows)


def fetch_calibration(url: str, key: str, cache_path: str | None = None, use_cache: bool = True) -> pd.DataFrame:
    """sensor_calibration: air/water/dry_soil/wet_soil + per-node GPS."""
    if cache_path is None:
        cache_path = _here(CACHE_DIR, "sensor_calibration_raw.json")
    if use_cache and os.path.exists(cache_path):
        rows = json.load(open(cache_path, encoding="utf-8"))
    else:
        session = _session(key)
        rows = _fetch_all(session, url, "sensor_calibration", "node_id,air,water,dry_soil,wet_soil,GPS")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(rows, open(cache_path, "w", encoding="utf-8"))
    df = pd.DataFrame(rows).set_index("node_id").sort_index()
    return df


def parse_gps(gps_str: str) -> tuple[float, float]:
    """'48.4566725N, 19.2319897E' -> (lat, lon), signed. Only N/E seen in
    this data; a S/W value would need a sign flip this parser doesn't do,
    since none exist in the live table to test against."""
    lat_s, lon_s = [p.strip() for p in gps_str.split(",")]
    lat = float(lat_s[:-1]) * (1 if lat_s[-1] == "N" else -1)
    lon = float(lon_s[:-1]) * (1 if lon_s[-1] == "E" else -1)
    return lat, lon


def filter_valid_nodes(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["node_id"].isin(NODE_IDS)].copy()


def dedupe_readings(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.sort_values("received_at")
    df = df.drop_duplicates(subset=DEDUPE_KEY_COLUMNS, keep="first")
    dropped = before - len(df)
    if dropped:
        print(f"dedupe_readings: dropped {dropped}/{before} duplicate-payload rows ({100*dropped/before:.1f}%)")
    return df


def resolve_timestamp(df: pd.DataFrame) -> pd.Series:
    """Epoch seconds per reading. received_at (server clock) is always
    trustworthy; recorded_at (node RTC) is trusted only if it's plausible
    (>= MIN_PLAUSIBLE_EPOCH) AND its gap from received_at fits the packet's
    expected class: near-zero for a live packet, up to
    BACKLOG_MAX_GAP_SECONDS for a replayed backlog packet. See config.py's
    comment for the live-data finding (a stale RTC value that passes a bare
    ">2020" test) that made the gap check necessary, not just the floor."""
    # .dt.as_unit("s") before .astype("int64") matters: pandas' datetime64
    # default resolution is version-dependent (ns historically, us as of
    # pandas 3.x, confirmed on the pandas 3.0.5 installed here) -- casting
    # straight to int64 silently gives the wrong unit depending on version.
    recv = pd.to_datetime(df["received_at"], utc=True).dt.as_unit("s").astype("int64")
    rec = df["recorded_at"].astype(float)
    gap = recv - rec  # positive: recorded_at is before received_at (normal)
    backlog = df["is_backlog"].astype(bool)
    max_gap = np.where(backlog, BACKLOG_MAX_GAP_SECONDS, NON_BACKLOG_MAX_GAP_SECONDS)
    plausible = (rec >= MIN_PLAUSIBLE_EPOCH) & (gap >= -60) & (gap <= max_gap)
    return pd.Series(np.where(plausible, rec, recv), index=df.index, dtype="int64")


def load_daily_raw_moisture(url: str, key: str, use_cache: bool = True) -> dict[int, pd.DataFrame]:
    """Fetch -> filter -> dedupe -> resolve timestamp -> daily aggregate of
    the RAW sensor column (not a calibrated/proxy value -- see README "Data"
    section for why this pipeline models `raw` directly).

    Returns {node_id: DataFrame[date-indexed] with columns raw_mean,
    raw_min, raw_max, n_readings}.
    """
    readings = fetch_readings_raw(url, key, use_cache=use_cache)
    readings = filter_valid_nodes(readings)
    readings = dedupe_readings(readings)

    readings["ts"] = resolve_timestamp(readings)
    readings["date"] = pd.to_datetime(readings["ts"], unit="s", utc=True).dt.floor("D")

    out: dict[int, pd.DataFrame] = {}
    for node_id, grp in readings.groupby("node_id"):
        daily = grp.groupby("date")["raw"].agg(raw_mean="mean", raw_min="min", raw_max="max", n_readings="size")
        daily = daily[daily["n_readings"] >= MIN_READINGS_PER_DAY]
        daily.index = daily.index.tz_localize(None)
        out[int(node_id)] = daily.sort_index()
    return out


def fetch_historical_daily(lat: float, lon: float, start_date: str, end_date: str,
                            cache_key: str, use_cache: bool = True, timeout: float = 30.0) -> pd.DataFrame:
    """Daily weather history for [start_date, end_date] at (lat, lon).
    Cached to disk keyed by cache_key (e.g. f"node{node_id}") since a given
    historical range never changes once past."""
    cache_path = _here(CACHE_DIR, f"weather_hist_{cache_key}_{start_date}_{end_date}.json")
    if use_cache and os.path.exists(cache_path):
        payload = json.load(open(cache_path, encoding="utf-8"))
    else:
        params = {"latitude": lat, "longitude": lon, "start_date": start_date, "end_date": end_date,
                   "daily": DAILY_VARS, "timezone": "UTC"}
        resp = requests.get(ARCHIVE_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(payload, open(cache_path, "w", encoding="utf-8"))

    daily = payload["daily"]
    df = pd.DataFrame({
        "precipitation_sum": daily["precipitation_sum"],
        "et0_fao_evapotranspiration": daily["et0_fao_evapotranspiration"],
        "temperature_2m_max": daily["temperature_2m_max"],
        "temperature_2m_min": daily["temperature_2m_min"],
        "relative_humidity_2m_mean": daily["relative_humidity_2m_mean"],
        "wind_speed_10m_max": daily["wind_speed_10m_max"],
        "shortwave_radiation_sum": daily["shortwave_radiation_sum"],
    }, index=pd.to_datetime(daily["time"]))
    df.attrs["elevation"] = payload.get("elevation")
    return df


def fetch_forecast_daily(lat: float, lon: float, days: int, cache_key: str,
                          use_cache: bool = False, timeout: float = 30.0) -> pd.DataFrame:
    """Forecast-endpoint daily weather for the next `days` days at (lat, lon).
    Not cached by default (a forecast goes stale fast) -- pass use_cache=True
    only for repeated test runs within the same day."""
    cache_path = _here(CACHE_DIR, f"weather_fcst_{cache_key}_{int(time.time()//3600)}.json")
    if use_cache and os.path.exists(cache_path):
        payload = json.load(open(cache_path, encoding="utf-8"))
    else:
        params = {"latitude": lat, "longitude": lon, "forecast_days": days,
                   "daily": DAILY_VARS, "timezone": "UTC"}
        resp = requests.get(FORECAST_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        if use_cache:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            json.dump(payload, open(cache_path, "w", encoding="utf-8"))

    daily = payload["daily"]
    df = pd.DataFrame({
        "precipitation_sum": daily["precipitation_sum"],
        "et0_fao_evapotranspiration": daily["et0_fao_evapotranspiration"],
        "temperature_2m_max": daily["temperature_2m_max"],
        "temperature_2m_min": daily["temperature_2m_min"],
        "relative_humidity_2m_mean": daily["relative_humidity_2m_mean"],
        "wind_speed_10m_max": daily["wind_speed_10m_max"],
        "shortwave_radiation_sum": daily["shortwave_radiation_sum"],
    }, index=pd.to_datetime(daily["time"]))
    df.attrs["elevation"] = payload.get("elevation")
    return df
