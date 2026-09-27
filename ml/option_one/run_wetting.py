"""Fit the wetting model (wetting.py) per node on nodes 1/4/5:
raw readings + station rain/ET0 -> rain events -> each node's measured drop
per event -> fit four variants (none / linear / threshold / store) ->
leave-one-event-out scores. Run with `python run_wetting.py` (needs .env).
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
import wetting
from config import CACHE_DIR, DRYDOWN_START, LOCAL_TZ, MODEL_NODE_IDS

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-scrape", action="store_true", help="Use the station database as-is.")
    args = parser.parse_args()
    out_dir = os.path.join(HERE, CACHE_DIR)
    os.makedirs(out_dir, exist_ok=True)

    print("=== 1/4 raw readings (Supabase, read-only) ===")
    url, key = data_supabase.load_credentials(os.path.join(HERE, ".env"))
    readings, cal = data_supabase.load_raw_readings(url, key, MODEL_NODE_IDS)
    print(f"  {len(readings)} cleaned readings\n")

    print("=== 2/4 station rain + ET0 ===")
    if not args.no_scrape:
        yesterday = datetime.now(meteotekov.STATION_TZ).date() - timedelta(days=1)
        meteotekov.scrape(meteotekov.date.fromisoformat(meteotekov.DEFAULT_START), yesterday, meteotekov.DEFAULT_DB)
    rain_min = wetting.station_rain_minutes()
    weather = station_weather.daily_pm_terms()
    weather = weather.reindex(pd.date_range(weather.index.min(), weather.index.max(), freq="D")).interpolate()
    rain_h = rain_min.resample("1h").sum()
    et_h = wetting.hourly_et0(weather["et0_mm"], LOCAL_TZ)
    rain_h = rain_h[et_h.index.min():et_h.index.max()]
    events = wetting.rain_events(rain_min[rain_h.index.min():rain_h.index.max() + pd.Timedelta("1h")])
    start = pd.Timestamp(DRYDOWN_START, tz=LOCAL_TZ)
    events = events[events.start >= start].reset_index(drop=True)
    print(f"  {len(events)} rain events >= {wetting.MIN_EVENT_MM} mm since {DRYDOWN_START}, "
          f"{events.mm.sum():.1f} mm total; store simulated from {rain_h.index.min():%Y-%m-%d}\n")

    print("=== 3/4 per-node responses, fits, leave-one-event-out ===")
    report, params_out = {}, {}
    for node_id in MODEL_NODE_IDS:
        g = readings[readings.node_id == node_id]
        hourly_local, daily = drydown.hourly_and_daily(g, LOCAL_TZ)
        threshold = drydown.wetting_threshold(hourly_local[DRYDOWN_START:])
        hourly = hourly_local.tz_convert("UTC")
        # wettings with no station rain from 18 h before onset to peak: wettings the
        # station can't explain; they stop other events' response windows
        # includes the slow (2-3 day) kind, e.g. node 1 on 08-24..08-27
        fast = drydown.detect_wettings(hourly_local, threshold)
        fast_days = {w["onset"].date() for w in fast}
        slow = [w for w in drydown.detect_slow_wettings(daily[DRYDOWN_START:], threshold, LOCAL_TZ)
                if not any(abs((w["onset"].date() - d).days) <= 2 for d in fast_days)]

        def rain_during(w):
            # slow peaks are day starts: the wettest point can be up to 24 h later
            until = w["peak"] + (pd.Timedelta("24h") if w.get("slow") else pd.Timedelta("1h"))
            return rain_min[w["onset"].tz_convert("UTC") - pd.Timedelta("18h"):until.tz_convert("UTC")].sum()

        unexplained = sorted((w for w in fast + slow if w["onset"] >= start and rain_during(w) < wetting.MIN_EVENT_MM),
                             key=lambda w: w["onset"])
        for w in slow:  # blocking spans for slow ones run to the end of the peak day
            w["peak"] = w["peak"] + pd.Timedelta("24h")
        resp = wetting.measure_responses(
            hourly, events, threshold,
            [(w["onset"].tz_convert("UTC"), w["peak"].tz_convert("UTC")) for w in unexplained])
        floor = float(min(cal.loc[node_id, "water"], g.raw.min()))
        observed = resp["drop"].to_numpy()
        print(f"\n  node {node_id}: {len(resp)} events scored, {int(resp.responded.sum())} responded "
              f"(drop > {threshold:.0f} counts); floor {floor:.0f}")

        scores, fits = {}, {}
        for model in wetting.MODELS:
            pred_obj = wetting.Predictor(model, resp, rain_h, et_h, floor)
            params = wetting.fit(pred_obj, observed)
            in_sample = pred_obj(params)
            loo = wetting.leave_one_out(pred_obj, observed)
            resp[f"pred_{model}"] = loo
            fits[model] = params
            scores[model] = {
                "params": params,
                "rmse_in_sample": _rmse(in_sample, observed),
                "rmse_loo": _rmse(loo, observed),
                "rmse_loo_responding": _rmse(loo[resp.responded], observed[resp.responded]),
                "hit_rate_loo": float(np.mean((loo > threshold) == resp.responded)),
            }
            print(f"    {model:9}  LOO RMSE {scores[model]['rmse_loo']:6.1f}  (responding events "
                  f"{scores[model]['rmse_loo_responding']:6.1f})  respond/not right {scores[model]['hit_rate_loo']:.0%}  "
                  + "  ".join(f"{k}={v:.2f}" for k, v in params.items()))
        best = min(scores, key=lambda m: scores[m]["rmse_loo"])
        print(f"    best on held-out events: {best}")
        print(f"    {'event start (local)':20}{'mm':>6}{'mm/h':>6}{'before':>8}{'observed':>9}{'store':>7}"
              f"{'thresh':>7}{'linear':>7}  delay first/peak")
        for _, r in resp.iterrows():
            delay = f"{r.hours_to_first:4.1f}h / {r.hours_to_peak:4.1f}h" if r.responded else ""
            print(f"    {r.start.tz_convert(LOCAL_TZ):%m-%d %H:%M}         {r.mm:6.1f}{r.peak_mm_h:6.1f}{r.x_before:8.0f}"
                  f"{r['drop']:9.0f}{r.pred_store:7.0f}{r.pred_threshold:7.0f}{r.pred_linear:7.0f}  {delay}")

        if unexplained:
            print(f"    wettings with no station rain (can't be modelled from station rain): "
                  + ", ".join(f"{w['onset']:%m-%d %Hh} ({w['size']:.0f})" for w in unexplained))

        resp.assign(start=resp.start.dt.tz_convert(LOCAL_TZ)).to_csv(
            os.path.join(out_dir, f"wetting_events_node{node_id}.csv"), index=False)
        report[str(node_id)] = {"threshold_counts": threshold, "floor_counts": floor, "best_loo": best,
                                "n_events": len(resp), "n_responded": int(resp.responded.sum()),
                                "models": scores,
                                "unexplained_wettings": [w["onset"].isoformat() for w in unexplained]}
        params_out[str(node_id)] = {"best_loo": best, **fits}

    print("\n=== 4/4 writing outputs ===")
    with open(os.path.join(out_dir, "wetting_params.json"), "w") as f:
        json.dump(params_out, f, indent=2)
    with open(os.path.join(out_dir, "wetting_validation.json"), "w") as f:
        json.dump(report, f, indent=2, default=float)
    print(f"  wetting_params.json, wetting_validation.json, wetting_events_node<N>.csv -> {out_dir}")
    return 0


def _rmse(pred, obs) -> float:
    return float(np.sqrt(np.mean((np.asarray(pred) - np.asarray(obs)) ** 2))) if len(obs) else float("nan")


if __name__ == "__main__":
    sys.exit(main())
