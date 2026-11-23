"""Resumable single-node validation driver.

NIGHT_SUMMARY.md's "missing piece": equifinality (12-seed refit) and
hold-out validation for nodes 1/4/5 need ~80-90 min of DE-solver compute
per node, but this environment kills background processes within a few
minutes regardless of declared timeout -- only foreground calls that
finish inside their own timeout survive (proven safe up to ~590s, one DE
fit at a time). This script runs exactly one seed's fit (or the hold-out
fit) per invocation, caching results to
reports/node_<id>_validation_cache.json, so the 13 fits equifinality+
hold-out need can be done as 13 separate foreground calls instead of one
long background job.

Usage (repeat --seed 0..11, then --holdout, then --finalize):
    python -m ml.option_three.validate_node --node 4 --seed 0
    python -m ml.option_three.validate_node --node 4 --holdout
    python -m ml.option_three.validate_node --node 4 --finalize
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from .configs import site
from .data import loaders, clean
from .events import windows as win
from .weather import subdaily
from .model.calibrate import calibrate_node, PARAM_ORDER
from .run_pipeline import build_window_data
from .eval import validate


def _cache_path(node_id: int):
    return site.OPTION_THREE_DIR / "reports" / f"node_{node_id}_validation_cache.json"


def _load_cache(node_id: int) -> dict:
    p = _cache_path(node_id)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"seeds": {}, "holdout": None}


def _save_cache(node_id: int, cache: dict) -> None:
    _cache_path(node_id).write_text(json.dumps(cache, indent=2, default=str), encoding="utf-8")


def _window_data(node_id: int, url: str, key: str):
    raw = loaders.fetch_readings_raw(url, key, site.NODE_IDS)
    prepared = clean.prepare_readings(raw, site.NODE_IDS)
    node_readings_raw = prepared[prepared["node_id"] == node_id]

    weather = loaders.fetch_hourly_weather(
        site.LAT, site.LON,
        start_date=node_readings_raw["ts"].min().date().isoformat(),
        end_date=node_readings_raw["ts"].max().date().isoformat(),
    )
    hourly_precip = pd.Series(
        weather["hourly"]["precipitation"].to_numpy(dtype=float),
        index=pd.DatetimeIndex(weather["hourly"]["time"]),
    )
    et0_series, et0_method = subdaily.hourly_et0(weather)

    cleaned = clean.clean_node(node_readings_raw, hourly_precip)
    rain_events = win.find_rain_events(hourly_precip)
    sign = win.detect_sign_convention(cleaned["clean"], rain_events)
    kept, _all_windows, _no_response = win.find_windows(node_id, cleaned["clean"], rain_events, sign)
    if len(kept) < 3:
        raise SystemExit(f"node {node_id}: only {len(kept)} usable windows, can't validate")
    return build_window_data(cleaned["clean"], kept, et0_series), et0_method


def _finalize(node_id: int, cache: dict) -> None:
    seeds = sorted(int(s) for s in cache["seeds"])
    if len(seeds) < 12:
        raise SystemExit(f"only {len(seeds)}/12 seeds cached: {seeds} -- run the missing ones first")
    if cache.get("holdout") is None:
        raise SystemExit("holdout not cached yet -- run --holdout first")

    fits = [cache["seeds"][str(s)] for s in seeds[:12]]
    per_param = {}
    for p in PARAM_ORDER:
        values = np.array([f["params"][p] for f in fits])
        mean = float(values.mean())
        std = float(values.std())
        per_param[p] = {"mean": mean, "std": std, "cv": (std / abs(mean)) if mean != 0 else float("inf")}
    kges = [f["kge"] for f in fits]
    equifinality_result = {
        "per_param": per_param,
        "kge_mean": float(np.mean(kges)),
        "kge_std": float(np.std(kges)),
    }

    holdout = cache["holdout"]
    main_fit = cache["seeds"]["0"]

    config_path = site.OPTION_THREE_DIR / "configs" / "nodes" / f"node_{node_id}.json"
    node_config = json.loads(config_path.read_text(encoding="utf-8"))
    node_config.pop("main_fit_only", None)
    node_config["params"] = main_fit["params"]
    node_config["kge"] = main_fit["kge"]
    node_config["equifinality_cv"] = {k: v["cv"] for k, v in per_param.items()}
    node_config["holdout_kge"] = holdout["held_out_kge"]
    config_path.write_text(json.dumps(node_config, indent=2), encoding="utf-8")

    out = {
        "node_id": node_id,
        "main_fit_only": False,
        "seed": 0,
        "kge": main_fit["kge"],
        "params": main_fit["params"],
        "equifinality": per_param,
        "equifinality_kge_mean": equifinality_result["kge_mean"],
        "equifinality_kge_std": equifinality_result["kge_std"],
        "holdout": holdout,
    }
    print(json.dumps(out, indent=2, default=str))

    cache["_equifinality_result"] = equifinality_result
    _save_cache(node_id, cache)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", type=int, required=True)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--holdout-index", type=int, default=0)
    ap.add_argument("--finalize", action="store_true")
    args = ap.parse_args()

    cache = _load_cache(args.node)

    if args.finalize:
        _finalize(args.node, cache)
        return

    if args.holdout:
        if cache.get("holdout") is not None:
            print("holdout already cached, skipping")
            return
        url, key = site.load_credentials()
        window_data, _ = _window_data(args.node, url, key)
        t0 = time.time()
        result = validate.holdout_validate(window_data, holdout_index=args.holdout_index, seed=0)
        print(f"holdout done in {time.time() - t0:.1f}s: held_out_kge={result['held_out_kge']:.4f}")
        cache["holdout"] = result
        _save_cache(args.node, cache)
        return

    if args.seed is None:
        raise SystemExit("pass --seed N, or --holdout, or --finalize")
    if str(args.seed) in cache["seeds"]:
        print(f"seed {args.seed} already cached, skipping")
        return

    url, key = site.load_credentials()
    window_data, _ = _window_data(args.node, url, key)
    t0 = time.time()
    fit = calibrate_node(window_data, seed=args.seed)
    print(f"seed {args.seed} done in {time.time() - t0:.1f}s: kge={fit['kge']:.4f} params={fit['params']}")
    cache["seeds"][str(args.seed)] = fit
    _save_cache(args.node, cache)


if __name__ == "__main__":
    main()
