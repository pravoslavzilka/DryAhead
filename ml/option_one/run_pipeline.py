"""End-to-end pipeline: confirm Supabase access -> pull + dedupe readings ->
pull matching Open-Meteo history -> calibrate per node (pooling Kc/p) ->
validate against persistence on the held-out tail -> equifinality check ->
ensemble forecast -> AWF drought index. Run with `python run_pipeline.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

import data_supabase
import data_weather
from calibrate import align_series, calibrate_all, check_equifinality
from config import CACHE_DIR, CALIBRATION_FRACTION, NODE_IDS
from config import SPINUP_DAYS as CFG_SPINUP
from forecast import forecast_node, summarize_forecast
from validate import validate_node

HERE = os.path.dirname(__file__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-days", type=int, default=35)
    parser.add_argument("--forecast-model", default="icon_seamless")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--maxiter", type=int, default=300, help="Differential evolution generations (lower = faster, less thorough).")
    parser.add_argument("--popsize", type=int, default=20, help="Differential evolution population multiplier.")
    parser.add_argument("--skip-equifinality", action="store_true", help="Skip the multi-start equifinality check (slow: ~8x a calibration).")
    parser.add_argument(
        "--pool-vegetation", action="store_true",
        help="Share Kc/p across all nodes (median of independent fits). Off by default -- "
             "only correct if every node genuinely sits under the same vegetation type.",
    )
    args = parser.parse_args()

    env_path = os.path.join(HERE, ".env")

    print("=== Step 1/6: confirming Supabase data access ===")
    url, key = data_supabase.load_credentials(env_path)
    data_supabase.check_access(url, key)
    print(f"OK -- connected to {url}, select access confirmed on readings + sensor_calibration.\n")

    print("=== Step 2/6: pulling + deduplicating sensor readings ===")
    daily_proxy = data_supabase.load_daily_theta_proxy(url, key)
    for node_id in NODE_IDS:
        s = daily_proxy.get(node_id)
        n = 0 if s is None else len(s)
        span = "" if not n else f" ({s.index.min().date()} to {s.index.max().date()})"
        print(f"  node {node_id}: {n} daily observations{span}")
    print()

    all_dates = pd.concat([s for s in daily_proxy.values() if len(s)]).index
    if len(all_dates) == 0:
        print("No usable daily observations -- nothing to calibrate against. Exiting.")
        return 1
    start = (all_dates.min() - pd.Timedelta(days=35)).strftime("%Y-%m-%d")
    end = min(all_dates.max(), pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"=== Step 3/6: pulling Open-Meteo historical weather ({start} to {end}) ===")
    weather = data_weather.fetch_historical_daily(start, end)
    print(f"  {len(weather)} days of rain_mm / et0_mm\n")

    node_data = {}
    for node_id, proxy in daily_proxy.items():
        if len(proxy) == 0:
            continue
        idx, rain, et0, obs = align_series(weather, proxy)
        node_data[node_id] = (rain, et0, obs)

    if not node_data:
        print("No node had enough daily coverage to calibrate. Exiting.")
        return 1

    n_days = len(weather)
    fit_end_idx = int(n_days * CALIBRATION_FRACTION)
    print(
        f"=== Step 4/6: calibrating ({len(node_data)} nodes, differential evolution, "
        f"KGE-scored, first {CALIBRATION_FRACTION:.0%} of {n_days} days) ==="
    )
    calibration = calibrate_all(
        node_data, fit_end_idx=fit_end_idx, seed=args.seed, maxiter=args.maxiter, popsize=args.popsize,
        pool_vegetation=args.pool_vegetation,
    )
    if calibration["pooled_shared"] is None:
        print("  Kc/p fit independently per node (--pool-vegetation not set).")
    else:
        print(f"  pooled (shared across nodes) Kc={calibration['pooled_shared']['Kc']:.3f}, "
              f"p={calibration['pooled_shared']['p']:.3f}  "
              f"(voted on by nodes {calibration['pooling_nodes']} -- others excluded: no in-sample "
              f"fit, or dead before the validation window opens)")
    for node_id, fit in calibration["final"].items():
        if not fit["valid"]:
            print(f"  node {node_id}: NO VALID FIT -- likely too little scorable data in the "
                  f"calibration window ({fit_end_idx - CFG_SPINUP} usable days at best; see README).")
            continue
        print(f"  node {node_id}: calibration-slice KGE={fit['kge']:.3f}  params={_round(fit['params'])}")
    print()

    print("=== Step 5/6: validating against persistence on the held-out tail ===")
    validation = {}
    for node_id, (rain, et0, obs) in node_data.items():
        if not calibration["final"][node_id]["valid"]:
            print(f"  node {node_id}: skipped (no valid calibration fit)")
            continue
        result = validate_node(rain, et0, obs, calibration["final"][node_id]["params"], fit_end_idx)
        validation[node_id] = result
        _print_validation(node_id, result)
    print()

    equifinality = {}
    if not args.skip_equifinality:
        print("=== Equifinality check (per node, 8 random restarts; slow) ===")
        for node_id, (rain, et0, obs) in node_data.items():
            summary = check_equifinality(
                rain, et0, obs, fixed_shared=calibration["pooled_shared"], n_starts=8,
                base_seed=args.seed + 1000 + node_id, maxiter=args.maxiter, popsize=args.popsize,
            )
            equifinality[node_id] = summary
            unconstrained = summary.index[~summary["well_constrained"]].tolist()
            print(f"  node {node_id}: not well-constrained by the data -> {unconstrained or 'none'}")
        print()

    print(f"=== Step 6/6: ensemble forecast ({args.forecast_days} days, model={args.forecast_model}) ===")
    try:
        ensemble = data_weather.fetch_forecast_ensemble(days=args.forecast_days, model=args.forecast_model)
    except Exception as exc:  # network/plan issues shouldn't crash the whole pipeline
        print(f"  forecast fetch failed ({exc}); skipping forecast step.")
        ensemble = None

    forecasts = {}
    if ensemble is not None:
        for node_id, (rain, et0, obs) in node_data.items():
            if not calibration["final"][node_id]["valid"]:
                continue
            params = calibration["final"][node_id]["params"]
            valid_obs = pd.Series(obs).dropna()
            if valid_obs.empty:
                continue
            current_proxy = valid_obs.iloc[-1]
            current_theta = params["cal_a"] * current_proxy + params["cal_b"]
            trajectories = forecast_node(params, current_theta, ensemble["rain_mm"], ensemble["et0_mm"])
            if trajectories.empty:
                continue
            summary = summarize_forecast(trajectories, params)
            forecasts[node_id] = summary
            last = summary.iloc[-1]
            print(
                f"  node {node_id}: day {args.forecast_days} AWF median={last['awf_p50']:.2f} "
                f"(p10={last['awf_p10']:.2f}, p90={last['awf_p90']:.2f}), "
                f"P(below wilting)={last['prob_below_wilting']:.0%}"
            )

    _write_outputs(calibration, validation, equifinality, forecasts)
    print(f"\nWrote fitted parameters, validation report and forecast summaries to {os.path.join(HERE, CACHE_DIR)}/")
    return 0


def _round(params: dict, digits: int = 3) -> dict:
    return {k: round(v, digits) for k, v in params.items()}


def _print_validation(node_id: int, result: dict) -> None:
    if "model" not in result:
        print(f"  node {node_id}: {result.get('note', 'no validation result')}")
        return
    m = result["model"]
    print(f"  node {node_id} ({result['n_val_days']} held-out days): model KGE={m['kge']:.3f} RMSE={m['rmse']:.4f}")
    for h in sorted(result["model_by_horizon"]):
        mh = result["model_by_horizon"][h]
        ph = result["persistence_by_horizon"][h]
        beats = "beats" if mh["rmse"] < ph["rmse"] else "loses to"
        print(f"    {h:>2}d ahead: model RMSE={mh['rmse']:.4f} vs persistence RMSE={ph['rmse']:.4f}  ({beats} persistence)")


def _write_outputs(calibration, validation, equifinality, forecasts) -> None:
    out_dir = os.path.join(HERE, CACHE_DIR)
    os.makedirs(out_dir, exist_ok=True)

    params_out = {
        "pooled_shared": calibration["pooled_shared"],
        "per_node": {str(k): v["params"] for k, v in calibration["final"].items()},
    }
    with open(os.path.join(out_dir, "fitted_params.json"), "w") as f:
        json.dump(params_out, f, indent=2)

    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, (np.floating, np.integer)):
            return obj.item()
        if isinstance(obj, float) and (obj != obj):  # NaN
            return None
        return obj

    val_out = {str(k): _clean(v) for k, v in validation.items()}
    with open(os.path.join(out_dir, "validation_report.json"), "w") as f:
        json.dump(val_out, f, indent=2)

    for node_id, summary in equifinality.items():
        summary.to_csv(os.path.join(out_dir, f"equifinality_node{node_id}.csv"))

    for node_id, summary in forecasts.items():
        summary.to_csv(os.path.join(out_dir, f"forecast_node{node_id}.csv"))


if __name__ == "__main__":
    sys.exit(main())
