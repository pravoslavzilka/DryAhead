"""Fit the drying model (drydown.py) per node on nodes 1/4/5:
load raw readings -> station weather terms -> detect wettings and cut drying
segments -> chronological 70/30 split -> fit (a/b split, plus the single-rate
baseline) -> score against persistence and average drift -> equifinality.
Run with `python run_drydown.py` from this folder (needs .env, see README).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import data_supabase
import drydown
import meteotekov
import station_weather
from config import CACHE_DIR, CALIBRATION_FRACTION, DRYDOWN_START, LOCAL_TZ, MODEL_NODE_IDS

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--maxiter", type=int, default=300)
    parser.add_argument("--popsize", type=int, default=20)
    parser.add_argument("--equifinality-starts", type=int, default=8, help="0 to skip")
    parser.add_argument("--no-scrape", action="store_true", help="Use the station database as-is.")
    args = parser.parse_args()
    out_dir = os.path.join(HERE, CACHE_DIR)
    os.makedirs(out_dir, exist_ok=True)

    print("=== 1/5 raw readings (Supabase, read-only) ===")
    url, key = data_supabase.load_credentials(os.path.join(HERE, ".env"))
    readings, cal = data_supabase.load_raw_readings(url, key, MODEL_NODE_IDS)
    print(f"  {len(readings)} cleaned readings for nodes {list(MODEL_NODE_IDS)}\n")

    print("=== 2/5 station weather (sun + air-drying terms) ===")
    yesterday = datetime.now(meteotekov.STATION_TZ).date() - timedelta(days=1)
    if not args.no_scrape:
        meteotekov.scrape(pd.Timestamp(DRYDOWN_START).date(), yesterday, meteotekov.DEFAULT_DB)
    weather = station_weather.daily_pm_terms()
    last_day = weather.index.max()
    full = pd.date_range(DRYDOWN_START, last_day, freq="D")
    missing = full.difference(weather.index)
    weather = weather.reindex(full).interpolate(limit_direction="both")
    print(f"  {len(full)} days {full[0].date()}..{last_day.date()}, {len(missing)} interpolated "
          f"{[d.date().isoformat() for d in missing] or ''}; "
          f"sun {weather.rad_mm.sum():.0f} mm + air {weather.aero_mm.sum():.0f} mm\n")

    split_day = full[0] + pd.Timedelta(days=int(len(full) * CALIBRATION_FRACTION))
    print(f"=== 3/5 drying segments (calibration before {split_day.date()}, validation from it) ===")
    per_node = {}
    for node_id in MODEL_NODE_IDS:
        hourly, daily = drydown.hourly_and_daily(readings[readings.node_id == node_id], LOCAL_TZ)
        threshold = drydown.wetting_threshold(hourly[DRYDOWN_START:])
        wettings = drydown.detect_wettings(hourly, threshold)
        fast_days = {w["onset"].date() for w in wettings}
        slow = [w for w in drydown.detect_slow_wettings(daily[DRYDOWN_START:], threshold, LOCAL_TZ)
                if not any(abs((w["onset"].date() - d).days) <= 2 for d in fast_days)]
        wettings = sorted(wettings + slow, key=lambda w: w["onset"])
        segments = drydown.build_segments(daily, wettings, DRYDOWN_START, str(last_day.date()))
        cal_segs, val_segs = drydown.split_segments(segments, split_day)
        per_node[node_id] = dict(daily=daily, threshold=threshold, wettings=wettings,
                                 segments=segments, cal=cal_segs, val=val_segs)
        kept = [w for w in wettings if w["onset"] >= pd.Timestamp(DRYDOWN_START, tz=LOCAL_TZ)]
        print(f"  node {node_id}: wetting threshold {threshold:.0f} counts; {len(kept)} wettings "
              f"({', '.join(w['onset'].strftime('%m-%d %Hh') for w in kept)})")
        for seg in segments:
            print(f"    segment {seg.index[0].date()}..{seg.index[-1].date()}  {seg.notna().sum():2d} days  "
                  f"raw {seg.dropna().iloc[0]:.0f} -> {seg.dropna().iloc[-1]:.0f}")
        print(f"    -> {len(cal_segs)} calibration segments ({sum(s.notna().sum() for s in cal_segs)} days), "
              f"{len(val_segs)} validation ({sum(s.notna().sum() for s in val_segs)} days)")
    print()

    print("=== 4/5 fitting + validation ===")
    report, params_out = {}, {}
    for node_id, nd in per_node.items():
        air, water = cal.loc[node_id, "air"], cal.loc[node_id, "water"]
        drift = drydown.mean_daily_drift(nd["cal"])
        node_rep = {"threshold_counts": nd["threshold"], "drift_counts_per_day": drift}
        for label, split in (("split_ab", True), ("single_rate", False)):
            fitted = drydown.fit(nd["cal"], weather, air, water, split, seed=args.seed + node_id,
                                 maxiter=args.maxiter, popsize=args.popsize)
            prm = drydown.DrydownParams(**fitted["params"])
            tables = {
                part: drydown.rmse_table(drydown.horizon_errors(segs, weather, prm, drift))
                for part, segs in (("calibration", nd["cal"]), ("validation", nd["val"]))
            }
            node_rep[label] = {"params": fitted["params"], "calibration_rmse": fitted["rmse"],
                               "rmse_by_horizon": {p: _table_json(t) for p, t in tables.items()}}
            params_out.setdefault(str(node_id), {})[label] = fitted["params"]
            print(f"  node {node_id} [{label}]  fit RMSE {fitted['rmse']:.1f} counts  "
                  + "  ".join(f"{k}={v:.3g}" for k, v in fitted["params"].items()
                              if split or k != "b"))
            _print_table(tables["validation"])
            if label == "split_ab":
                nd["prm"] = prm
        report[str(node_id)] = node_rep
        print()

    equifinality = {}
    if args.equifinality_starts:
        print(f"=== 5/5 equifinality ({args.equifinality_starts} random restarts, split_ab) ===")
        for node_id, nd in per_node.items():
            air, water = cal.loc[node_id, "air"], cal.loc[node_id, "water"]
            summary = drydown.check_equifinality(nd["cal"], weather, air, water, True, args.equifinality_starts,
                                                 base_seed=args.seed + 1000 + node_id,
                                                 maxiter=args.maxiter, popsize=args.popsize)
            equifinality[node_id] = summary
            summary.to_csv(os.path.join(out_dir, f"drydown_equifinality_node{node_id}.csv"))
            loose = summary.index[~summary["well_constrained"]].tolist()
            print(f"  node {node_id}: not pinned down by the data -> {loose or 'none'}")
            print("    " + summary.round(3).to_string().replace("\n", "\n    "))

    for node_id, nd in per_node.items():
        rows = []
        for part, segs in (("calibration", nd["cal"]), ("validation", nd["val"])):
            for k, seg in enumerate(segs):
                rad, aero = drydown.forcing(seg, weather)
                sim = drydown.simulate(seg.iloc[0], rad, aero, nd["prm"])
                rows.append(pd.DataFrame({"part": part, "segment": k, "observed_raw": seg.to_numpy(),
                                          "simulated_raw": sim}, index=seg.index.rename("date")))
        pd.concat(rows).to_csv(os.path.join(out_dir, f"drydown_segments_node{node_id}.csv"))
    with open(os.path.join(out_dir, "drydown_params.json"), "w") as f:
        json.dump(params_out, f, indent=2)
    with open(os.path.join(out_dir, "drydown_validation.json"), "w") as f:
        json.dump(report, f, indent=2, default=float)
    print(f"\nWrote drydown_params.json, drydown_validation.json, drydown_segments_node<N>.csv, "
          f"drydown_equifinality_node<N>.csv to {out_dir}")
    return 0


def _table_json(t: pd.DataFrame) -> dict:
    if t.empty:
        return {}
    return {int(h): {pred: {"rmse": float(t.loc[h, ("rmse", pred)]), "n": int(t.loc[h, ("n", pred)])}
                     for pred in t["rmse"].columns if not np.isnan(t.loc[h, ("rmse", pred)])}
            for h in t.index}


def _print_table(t: pd.DataFrame) -> None:
    if t.empty:
        print("    validation: no held-out segments")
        return
    for h in t.index:
        r = t.loc[h, "rmse"]
        best = r.idxmin()
        print(f"    validation {h:>2}d ahead (n={int(t.loc[h, ('n', 'model')])}): model {r['model']:6.1f}  "
              f"persistence {r['persistence']:6.1f}  drift {r['drift']:6.1f}   best: {best}")


if __name__ == "__main__":
    sys.exit(main())
