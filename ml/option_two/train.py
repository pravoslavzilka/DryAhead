#!/usr/bin/env python3
"""CLI entry point: pull data, build the feature table, evaluate every
horizon (CV + leave-one-node-out vs. persistence), fit final models, save
plots + a markdown results summary + the fitted models to outputs/.

Run from ml/option_two/: `python train.py`
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pickle
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning, module="lightgbm")

import numpy as np
import pandas as pd

from config import HORIZONS, OUTPUTS_DIR, ROLLING_WINDOWS
from ingest import features, loaders
from eval import baselines, report
from modeling import gbm


def build_dataset(use_cache: bool = True) -> pd.DataFrame:
    url, key = loaders.load_credentials()
    loaders.check_access(url, key)
    moisture = loaders.load_daily_raw_moisture(url, key, use_cache=use_cache)
    cal = loaders.fetch_calibration(url, key, use_cache=use_cache)

    buffer_days = max(ROLLING_WINDOWS)
    weather, elevation = {}, {}
    for node_id, m in moisture.items():
        lat, lon = loaders.parse_gps(cal.loc[node_id, "GPS"])
        start = (m.index.min() - datetime.timedelta(days=buffer_days)).strftime("%Y-%m-%d")
        end = m.index.max().strftime("%Y-%m-%d")
        w = loaders.fetch_historical_daily(lat, lon, start, end, cache_key=f"node{node_id}", use_cache=use_cache)
        weather[node_id] = w
        elevation[node_id] = w.attrs.get("elevation")

    return features.build_feature_table(moisture, weather, elevation, HORIZONS)


def _fmt_metrics(m: dict) -> str:
    return f"RMSE={m['rmse']:.1f}  MAE={m['mae']:.1f}  KGE={m['kge']:.3f}  NSE={m['nse']:.3f}"


def run(use_cache: bool = True) -> dict:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    table = build_dataset(use_cache=use_cache)
    table.to_parquet(os.path.join(OUTPUTS_DIR, "feature_table.parquet"))

    events = report.effective_event_count(table)
    row_counts = table.groupby("node_id").size().to_dict()

    all_results = {}
    lines = ["# option_two (gradient boosting) -- results\n"]
    lines.append(f"Row count per node (all calendar days in each node's own record, not all usable "
                  f"for every horizon): {row_counts}\n")
    lines.append(f"Effective independent wetting events per node (see eval/report.py "
                  f"effective_event_count for the exact definition): {events} "
                  f"-- total {sum(events.values())} events across {len(events)} nodes.\n")
    lines.append("This is the number that should calibrate how much to trust any of the numbers "
                  "below, not the row counts above.\n")

    lines.append("\n## Model vs. persistence, by horizon\n")
    lines.append("| Horizon | CV: model RMSE | CV: persistence RMSE | CV: model KGE | "
                  "LONO: model RMSE | LONO: persistence RMSE | LONO: model KGE | Beats persistence? |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for h in HORIZONS:
        res = report.evaluate_horizon(table, h)
        all_results[h] = res

        cv_m = res.get("cv_model")
        cv_p = res.get("cv_persistence")
        lono_m = res.get("lono_model")
        lono_p = res.get("lono_persistence")

        beats = "?"
        if cv_m and cv_p:
            beats = "YES" if cv_m["rmse"] < cv_p["rmse"] else "no"

        def fmt_rmse(m):
            return f"{m['rmse']:.1f}" if m else "n/a"

        def fmt_kge(m):
            return f"{m['kge']:.3f}" if m else "n/a"

        lines.append(
            f"| h={h}d | {fmt_rmse(cv_m)} | {fmt_rmse(cv_p)} | {fmt_kge(cv_m)} | "
            f"{fmt_rmse(lono_m)} | {fmt_rmse(lono_p)} | {fmt_kge(lono_m)} | {beats} |"
        )

        if cv_m:
            report.save_scatter_plot(res["cv_pred"], res["cv_obs"], h,
                                      os.path.join(OUTPUTS_DIR, f"scatter_h{h}.png"))
            dates = table.loc[table[f"target_h{h}"].notna(), "date"]
            # cv_pred/cv_obs are concatenated across folds in date order per
            # fold already; align a matching date vector the same way for
            # the timeseries plot (approximate -- folds are chronological
            # and non-overlapping, so concatenation order is calendar order).
            report.save_timeseries_plot(dates.iloc[-len(res["cv_obs"]):] if len(dates) >= len(res["cv_obs"]) else dates,
                                         res["cv_pred"], res["cv_obs"], h,
                                         os.path.join(OUTPUTS_DIR, f"timeseries_h{h}.png"))

    print("\n".join(lines))
    return {"table": table, "results": all_results, "events": events, "row_counts": row_counts, "lines": lines}


def fit_and_save_final_models(table: pd.DataFrame) -> None:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    for h in HORIZONS:
        fit = gbm.fit_final_models(table, h)
        with open(os.path.join(OUTPUTS_DIR, f"model_h{h}.pkl"), "wb") as f:
            pickle.dump(fit, f)


def run_shap(table: pd.DataFrame) -> dict:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    importances = {}
    for h in HORIZONS:
        imp = report.save_shap_plot(table, h, os.path.join(OUTPUTS_DIR, f"shap_h{h}.png"))
        importances[h] = imp
    with open(os.path.join(OUTPUTS_DIR, "shap_importance.json"), "w") as f:
        json.dump(importances, f, indent=2)
    return importances


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-cache", action="store_true", help="Re-fetch from Supabase/Open-Meteo instead of using cached ingest/cache/*.json")
    parser.add_argument("--skip-shap", action="store_true")
    args = parser.parse_args()

    out = run(use_cache=not args.no_cache)
    fit_and_save_final_models(out["table"])
    if not args.skip_shap:
        run_shap(out["table"])
    print(f"\nOutputs written to {OUTPUTS_DIR}/")
