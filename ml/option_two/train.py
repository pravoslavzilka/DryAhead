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


def build_dataset(use_cache: bool = True) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Returns (feature table, per-node daily weather, calibration table).
    The latter two are only needed by the water-balance baseline
    (eval/baselines.add_water_balance_columns) -- returned here rather than
    re-fetched there so both paths share exactly the same per-node
    lat/lon/date-range logic instead of risking the two drifting apart."""
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

    table = features.build_feature_table(moisture, weather, elevation, HORIZONS)
    return table, weather, cal


def _fmt_metrics(m: dict) -> str:
    return f"RMSE={m['rmse']:.1f}  MAE={m['mae']:.1f}  KGE={m['kge']:.3f}  NSE={m['nse']:.3f}"


def run(use_cache: bool = True) -> dict:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    table, weather_by_node, cal = build_dataset(use_cache=use_cache)
    table = baselines.add_water_balance_columns(table, weather_by_node, cal, HORIZONS)
    table.to_parquet(os.path.join(OUTPUTS_DIR, "feature_table.parquet"))

    wb_available = baselines.water_balance_available()

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
    if not wb_available:
        lines.append("\n_Water-balance baseline (option_one's bucket model) skipped: "
                      "ml/option_one/bucket_model.py or its fitted_params.json isn't available._\n")

    lines.append("\n## Model vs. persistence" + (" vs. water balance" if wb_available else "") + ", by horizon\n")
    header = ("| Horizon | CV: model RMSE | CV: persistence RMSE" +
              (" | CV: water-balance RMSE (n)" if wb_available else "") +
              " | CV: model KGE | LONO: model RMSE | LONO: persistence RMSE" +
              (" | LONO: water-balance RMSE (n)" if wb_available else "") +
              " | LONO: model KGE | Beats persistence? |")
    lines.append(header)
    lines.append("|---" * header.count("|") + "|")

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

        def fmt_wb(metrics_key, n_key):
            m = res.get(metrics_key)
            if not m:
                return "n/a"
            return f"{m['rmse']:.1f} (n={res.get(n_key)})"

        row = f"| h={h}d | {fmt_rmse(cv_m)} | {fmt_rmse(cv_p)} |"
        if wb_available:
            row += f" {fmt_wb('cv_water_balance', 'cv_water_balance_n')} |"
        row += f" {fmt_kge(cv_m)} | {fmt_rmse(lono_m)} | {fmt_rmse(lono_p)} |"
        if wb_available:
            row += f" {fmt_wb('lono_water_balance', 'lono_water_balance_n')} |"
        row += f" {fmt_kge(lono_m)} | {beats} |"
        lines.append(row)

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
    _write_full_metrics(all_results, events, row_counts)
    return {"table": table, "results": all_results, "events": events, "row_counts": row_counts, "lines": lines}


def _write_full_metrics(all_results: dict, events: dict, row_counts: dict) -> None:
    """outputs/full_metrics.json -- full RMSE/MAE/KGE/NSE for every
    horizon x evaluation mode (model, persistence, water-balance
    held-out, water-balance all-rows), referenced from README.md/
    NIGHT_SUMMARY.md as the place to find numbers not in the summary
    tables. Drops the raw pred/obs arrays (those are what the scatter/
    timeseries plots are for, not this file) and stringifies the one
    Timestamp value (water_balance_held_out_cutoff)."""
    skip_keys = {"cv_pred", "cv_obs", "lono_pred", "lono_obs"}
    out = {}
    for h, res in all_results.items():
        clean = {k: v for k, v in res.items() if k not in skip_keys}
        if "water_balance_held_out_cutoff" in clean:
            clean["water_balance_held_out_cutoff"] = str(clean["water_balance_held_out_cutoff"])
        out[str(h)] = clean
    out["_events"] = {str(k): v for k, v in events.items()}
    out["_row_counts"] = {str(k): v for k, v in row_counts.items()}
    with open(os.path.join(OUTPUTS_DIR, "full_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


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
