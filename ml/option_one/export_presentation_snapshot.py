"""Static data snapshot for the Blue Challenge presentation page
(frontend/blue/, served at /blue). The page must work with Supabase down, so
every chart reads this file, bundled at build time.

Writes frontend/src/blue/snapshot.json:
  - daily soil humidity (%, same scale as the dashboard) per node
  - station rain per day
  - a drying-model forecast vs measurement vs persistence, from run_drydown.py
  - held-out scores per node, and a few findings computed from the data
Prints the findings so they can be checked before they go on the page.

Run: `python export_presentation_snapshot.py` (needs .env and outputs/ from
run_drydown.py). Re-run and rebuild to refresh the page's data.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

import data_supabase
import station_weather
import wetting
from config import LOCAL_TZ

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "..", "frontend", "src", "blue", "snapshot.json")

CHART_NODES = (1, 3, 4, 5)  # 2 reported for only ~10 days
START = "2026-06-30"  # sensors settled after installation on 06-29
MIN_READINGS_PER_DAY = 20


def main() -> int:
    url, key = data_supabase.load_credentials(os.path.join(HERE, ".env"))
    cal = data_supabase.fetch_calibration(url, key)
    all_rows = data_supabase.dedupe_readings(data_supabase.filter_valid_nodes(data_supabase.fetch_readings(url, key)))
    all_rows["ts"] = pd.to_datetime(data_supabase.resolve_timestamp(all_rows), unit="s", utc=True)
    all_rows = all_rows[all_rows.ts >= "2026-01-01"]
    readings = data_supabase.clean_raw_readings(all_rows[all_rows.node_id.isin(CHART_NODES)].copy(), cal)

    yesterday = (pd.Timestamp.now(tz=LOCAL_TZ).normalize() - pd.Timedelta(days=1)).tz_localize(None)
    days = pd.date_range(START, yesterday, freq="D")

    nodes = {}
    for n in CHART_NODES:
        g = readings[readings.node_id == n]
        air, water = cal.loc[n, "air"], cal.loc[n, "water"]
        pct = ((air - g.raw) / (air - water) * 100).clip(0, 100)
        s = pd.Series(pct.to_numpy(), index=g.ts.dt.tz_convert(LOCAL_TZ).to_numpy())
        daily = s.resample("1D").agg(["median", "size"])
        daily = daily["median"].where(daily["size"] >= MIN_READINGS_PER_DAY)
        daily.index = daily.index.tz_localize(None)
        daily = daily.reindex(days)
        last = daily.last_valid_index()
        nodes[str(n)] = {
            "humidity": [None if np.isnan(v) else round(float(v), 1) for v in daily],
            "last_day": last.date().isoformat() if last is not None else None,
        }

    rain_min = wetting.station_rain_minutes()
    rain_local = rain_min.tz_convert(LOCAL_TZ).resample("1D").sum()
    rain_local.index = rain_local.index.tz_localize(None)
    rain = rain_local.reindex(days)

    # --- forecast demo: node 4's held-out segment, model vs measured vs persistence
    seg = pd.read_csv(os.path.join(HERE, "outputs", "drydown_segments_node4.csv"), parse_dates=["date"])
    val = seg[seg.part == "validation"]
    demo_seg = val[val.segment == val.segment.max()]
    a4, w4 = cal.loc[4, "air"], cal.loc[4, "water"]
    # clamped to 0-100 like the dashboard (raw can pass the wet calibration point)
    to_pct = lambda raw: round(float(min(100.0, max(0.0, (a4 - raw) / (a4 - w4) * 100))), 2)
    demo = {
        "node": 4,
        "dates": [d.date().isoformat() for d in demo_seg.date],
        "measured": [None if np.isnan(v) else to_pct(v) for v in demo_seg.observed_raw],
        "model": [to_pct(v) for v in demo_seg.simulated_raw],
        "persistence": to_pct(demo_seg.observed_raw.dropna().iloc[0]),
    }

    with open(os.path.join(HERE, "outputs", "drydown_validation.json")) as f:
        dval = json.load(f)
    scores = {}
    for n in ("1", "4", "5"):
        span = abs(cal.loc[int(n), "air"] - cal.loc[int(n), "water"]) / 100  # counts per % point
        h7 = dval[n]["single_rate"]["rmse_by_horizon"]["validation"].get("7", {})
        scores[n] = {k: round(h7[k]["rmse"] / span, 2) for k in ("model", "persistence", "drift") if k in h7}
        scores[n]["n"] = h7.get("model", {}).get("n")

    # --- findings, computed (printed for review) -----------------------------
    hum = pd.DataFrame({n: pd.Series(v["humidity"], index=days, dtype=float) for n, v in nodes.items()})
    findings = {}

    storm = pd.Timestamp("2026-07-15")
    before = hum.loc[storm - pd.Timedelta(days=1)]
    after = hum.loc[storm + pd.Timedelta(days=1)]
    findings["storm_0715"] = {
        "rain_mm": round(float(rain.loc[storm]), 1),
        "change_pp": {n: None if np.isnan(after[n] - before[n]) else round(float(after[n] - before[n]), 1) for n in hum},
    }

    # node 4 after the storm: how long it stayed wetter than it was before
    n4 = hum["4"][storm:]
    back = n4[n4 <= before["4"] + 5].first_valid_index()
    findings["node4_after_storm"] = {
        "before": round(float(before["4"]), 1),
        "day_after": round(float(after["4"]), 1),
        "after_35_days": round(float(hum["4"].loc[storm + pd.Timedelta(days=35)]), 1),
        "days_until_within_5pp_of_before": None if back is None else int((back - storm).days),
    }

    dry_from, dry_to = pd.Timestamp("2026-07-24"), pd.Timestamp("2026-08-16")
    findings["dry_spell_0724_0816"] = {
        "days": int((dry_to - dry_from).days + 1),
        "rain_mm": round(float(rain[dry_from:dry_to].sum()), 1),
        "change_pp": {n: None if np.isnan(hum[n][dry_to] - hum[n][dry_from]) else round(float(hum[n][dry_to] - hum[n][dry_from]), 1) for n in hum},
    }
    findings["small_rain_note"] = "events of 1-3 mm: 0 of 6 raised humidity at nodes 4 and 5 (run_wetting.py)"

    total_measurements = int(len(all_rows))
    out = {
        "generated": date.today().isoformat(),
        "start": START,
        "days": [d.date().isoformat() for d in days],
        "nodes": nodes,
        "rain_mm": [round(float(v), 1) for v in rain.fillna(0)],
        "total_measurements": total_measurements,
        "first_measurement": all_rows.ts.min().date().isoformat(),
        "forecast_demo": demo,
        "scores_7d_pp": scores,
        "findings": findings,
    }
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    with open(TARGET, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(json.dumps({k: out[k] for k in ("total_measurements", "first_measurement", "scores_7d_pp", "findings")}, indent=2))
    print(f"demo: node 4 {demo['dates'][0]}..{demo['dates'][-1]}")
    print(f"wrote {os.path.normpath(TARGET)} ({os.path.getsize(TARGET) / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
