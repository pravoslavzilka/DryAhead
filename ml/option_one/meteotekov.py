"""Scrape the meteotekov.sk Zajezova station's daily archive into a local
SQLite database -- a ground-truth rain record from the station next to the
nodes, to check against (or replace) Open-Meteo's gridded precipitation.

Each archive page (https://meteotekov.sk/@zajezova/statistiky/archiv/YYYY-MM-DD)
ends with a table of ~1-minute observations for that local day. Every row is
stored as-is in `observations`; `daily_precipitation` is a view over it.

Note on "Zrazky" (precipitation): the station reports a running total that
resets at local midnight, not a per-minute amount -- so a day's rain is the
day's max, not a sum. Times are station-local (Europe/Bratislava); a UTC
timestamp is stored alongside because the rest of this pipeline works in UTC
days (data_weather.py).

This station is the pipeline's rain source for calibration (run_pipeline.py
--rain-source, default "station"): it sits in the same area as the nodes, and
over summer 2026 Open-Meteo's grid misplaced or missed the convective storms
that matter most (e.g. 24.7 mm measured on 2026-07-15 vs 1.3 mm gridded).

Run directly: `python meteotekov.py` (stdlib only, no network beyond the
station site). Re-running skips days already stored, so it's resumable.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import unescape
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "data", "meteotekov_zajezova.sqlite")

ARCHIVE_URL = "https://meteotekov.sk/@zajezova/statistiky/archiv/{day}"
USER_AGENT = "DryAhead-research/0.1 (soil-moisture research; polite daily-archive fetch)"
STATION_TZ = ZoneInfo("Europe/Bratislava")

# Earliest usable node data per README.md ("56 usable days from 2026-06-29").
DEFAULT_START = "2026-06-29"
REQUEST_DELAY_SECONDS = 2.0

# Table header (Slovak) -> column name. Parsing goes by header, not position,
# so a reordered or extended table fails loudly instead of misfiling values.
COLUMNS = {
    "Teplota": "temperature_c",
    "Vlhkosť": "humidity_pct",
    "Tlak": "pressure_hpa",
    "Rýchlosť vetra": "wind_speed_kmh",
    "Nárazy vetra": "wind_gust_kmh",
    "Smer vetra": "wind_dir",
    "Zrážky": "precip_cum_mm",
    "Sln. žiarenie": "solar_wm2",
    "UV index": "uv_index",
}
TEXT_COLUMNS = {"wind_dir"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    date           TEXT NOT NULL,   -- station-local day, YYYY-MM-DD
    time           TEXT NOT NULL,   -- station-local HH:MM
    ts_utc         TEXT NOT NULL,   -- ISO 8601 UTC
    temperature_c  REAL,
    humidity_pct   REAL,
    pressure_hpa   REAL,
    wind_speed_kmh REAL,
    wind_gust_kmh  REAL,
    wind_dir       TEXT,
    precip_cum_mm  REAL,            -- running daily total, resets at local midnight
    solar_wm2      REAL,
    uv_index       REAL,
    PRIMARY KEY (date, time)
);

CREATE TABLE IF NOT EXISTS fetched_days (
    date           TEXT PRIMARY KEY,
    n_reported     INTEGER,         -- "bolo zaznamenanych N merani" on the page
    n_stored       INTEGER,
    fetched_at     TEXT NOT NULL,
    source_url     TEXT NOT NULL
);

CREATE VIEW IF NOT EXISTS daily_precipitation AS
SELECT date,
       MAX(precip_cum_mm) AS precip_mm,
       COUNT(*)           AS n_observations
FROM observations
GROUP BY date;
"""


class ScrapeError(RuntimeError):
    pass


def fetch_page(day: date, timeout: float = 30.0, retries: int = 2) -> str:
    url = ARCHIVE_URL.format(day=day.isoformat())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries:
                raise ScrapeError(f"{url}: {exc}") from exc
            time.sleep(REQUEST_DELAY_SECONDS * 5 * (attempt + 1))
    raise AssertionError("unreachable")


def _cell_text(cell_html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", cell_html)).strip()


def _number(text: str) -> float | None:
    m = re.match(r"-?\d+(?:\.\d+)?", text.replace(",", "."))
    return float(m.group()) if m else None


def parse_page(html: str, day: date) -> tuple[int | None, list[dict]]:
    """Returns (measurement count the page reports, parsed rows)."""
    table = re.search(r"<table[^>]*>(.*?)</table>", html, re.S)
    if table is None:
        raise ScrapeError(f"{day}: no observations table on page")
    body = table.group(1)

    # The page shows the day it actually rendered; out-of-range dates can
    # fall back to another day, which must not be stored under `day`.
    shown = re.search(r"Dňa <strong>(\d{2})\.(\d{2})\.(\d{4})</strong>", body)
    if shown is None or date(int(shown[3]), int(shown[2]), int(shown[1])) != day:
        raise ScrapeError(f"{day}: page does not show data for the requested day")
    reported = re.search(r"zaznamenaných <strong>(\d+)</strong>", body)
    n_reported = int(reported[1]) if reported else None

    headers = [_cell_text(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", body, re.S)]
    if not headers or headers[0] != "Čas" or any(h not in COLUMNS for h in headers[1:]):
        raise ScrapeError(f"{day}: unexpected table header {headers}")
    names = [COLUMNS[h] for h in headers[1:]]

    rows = []
    for tr in re.findall(r"<tr id=\"[\d:]+\">(.*?)</tr>", body, re.S):
        cells = [_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) != len(headers):
            raise ScrapeError(f"{day}: row has {len(cells)} cells, header has {len(headers)}")
        hh, mm = (int(x) for x in cells[0].split(":"))
        local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=STATION_TZ)
        row = {
            "date": day.isoformat(),
            "time": cells[0],
            "ts_utc": local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for name, text in zip(names, cells[1:]):
            row[name] = (text or None) if name in TEXT_COLUMNS else _number(text)
        rows.append(row)
    return n_reported, rows


def store_day(conn: sqlite3.Connection, day: date, n_reported: int | None, rows: list[dict]) -> None:
    cols = ["date", "time", "ts_utc", *COLUMNS.values()]
    with conn:
        conn.execute("DELETE FROM observations WHERE date = ?", (day.isoformat(),))
        conn.executemany(
            f"INSERT OR REPLACE INTO observations ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [tuple(r.get(c) for c in cols) for r in rows],
        )
        conn.execute(
            "INSERT OR REPLACE INTO fetched_days VALUES (?, ?, ?, ?, ?)",
            (
                day.isoformat(), n_reported, len(rows),
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ARCHIVE_URL.format(day=day.isoformat()),
            ),
        )


def open_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def scrape(start: date, end: date, db_path: str, refetch: bool = False) -> int:
    conn = open_db(db_path)
    done = {r[0] for r in conn.execute("SELECT date FROM fetched_days")}
    days = [start + timedelta(d) for d in range((end - start).days + 1)]
    todo = [d for d in days if refetch or d.isoformat() not in done]
    print(f"{len(days)} days in range, {len(days) - len(todo)} already stored, fetching {len(todo)}")

    failures = []
    for i, day in enumerate(todo, 1):
        try:
            n_reported, rows = parse_page(fetch_page(day), day)
            store_day(conn, day, n_reported, rows)
            total = max((r["precip_cum_mm"] or 0.0 for r in rows), default=0.0)
            print(f"  [{i}/{len(todo)}] {day}: {len(rows)} rows (page reports {n_reported}), rain {total:.1f} mm", flush=True)
        except ScrapeError as exc:
            failures.append(day)
            print(f"  [{i}/{len(todo)}] {day}: FAILED -- {exc}", flush=True)
        if i < len(todo):
            time.sleep(REQUEST_DELAY_SECONDS)

    conn.close()
    if failures:
        print(f"{len(failures)} day(s) failed: {', '.join(d.isoformat() for d in failures)} -- re-run to retry")
    print(f"Database: {db_path}")
    return 1 if failures else 0


def daily_rain_utc(start: date, end: date, db_path: str = DEFAULT_DB) -> dict[str, float]:
    """Station rain per UTC day (mm), for UTC days in [start, end] the
    database fully covers -- matching data_weather's timezone="UTC" days.

    Built from per-minute increments of the running local-day total, so rain
    lands in the UTC day it actually fell in. A UTC day spans two local days
    (it starts at 01:00/02:00 local), so it's only returned when both are
    stored; callers fill anything missing from another source. A missing
    cell ("--,- mm") is carried forward: rain during the gap shows up in the
    next reading's increment, unless the gap crosses local midnight.
    """
    conn = open_db(db_path)
    fetched = {r[0] for r in conn.execute("SELECT date FROM fetched_days")}
    totals: dict[str, float] = {}
    prev_day, last = None, 0.0
    rows = conn.execute(
        "SELECT date, ts_utc, precip_cum_mm FROM observations WHERE date BETWEEN ? AND ? ORDER BY date, time",
        (start.isoformat(), (end + timedelta(days=1)).isoformat()),
    )
    for local_day, ts_utc, cum in rows:
        if local_day != prev_day:
            prev_day, last = local_day, 0.0
        if cum is None:
            continue
        totals[ts_utc[:10]] = totals.get(ts_utc[:10], 0.0) + max(cum - last, 0.0)
        last = cum
    conn.close()

    covered = {}
    for d in (start + timedelta(n) for n in range((end - start).days + 1)):
        if d.isoformat() in fetched and (d + timedelta(days=1)).isoformat() in fetched:
            covered[d.isoformat()] = round(totals.get(d.isoformat(), 0.0), 2)
    return covered


def main() -> int:
    yesterday = datetime.now(STATION_TZ).date() - timedelta(days=1)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default=DEFAULT_START, help=f"first local day, YYYY-MM-DD (default {DEFAULT_START})")
    parser.add_argument("--end", default=yesterday.isoformat(), help="last local day (default: yesterday -- today is incomplete)")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--refetch", action="store_true", help="re-download days already in the database")
    args = parser.parse_args()
    return scrape(date.fromisoformat(args.start), date.fromisoformat(args.end), args.db, refetch=args.refetch)


if __name__ == "__main__":
    sys.exit(main())
