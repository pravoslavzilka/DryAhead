#!/usr/bin/env python3
"""Load saved models + current data + a weather forecast, produce a
prediction interval (quantile alphas from config.QUANTILE_ALPHAS) per node
per horizon.

Run from ml/option_two/ after `python train.py` has produced outputs/model_h*.pkl:
    python predict.py [--node NODE_ID]
"""

from __future__ import annotations

import argparse
import datetime
import os
import pickle

import pandas as pd

from config import HORIZONS, OUTPUTS_DIR, QUANTILE_ALPHAS, ROLLING_WINDOWS
from ingest import features, loaders


def latest_feature_row(node_id: int) -> pd.Series | None:
    """The most recent usable row of the cached feature table for a node
    (built by train.py's run()) -- this is "today" as far as this pipeline
    is concerned; predict.py does not itself re-run the weather-forecast
    join into a live extrapolated row (see README "Known limitations" for
    why: the forecast endpoint's variables don't backfill lag_moisture_t*,
    only the weather-derived columns, so a fully forecast-driven future row
    needs the recursive-vs-direct distinction handled explicitly, not
    silently -- out of scope for this pass, flagged in NIGHT_SUMMARY.md)."""
    path = os.path.join(OUTPUTS_DIR, "feature_table.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found -- run train.py first.")
    table = pd.read_parquet(path)
    node_rows = table[(table["node_id"] == node_id) & table["theta_raw"].notna()].sort_values("date")
    if node_rows.empty:
        return None
    return node_rows.iloc[-1]


def predict_node(node_id: int) -> dict:
    row = latest_feature_row(node_id)
    if row is None:
        return {}
    from ingest.features import FEATURE_COLUMNS
    X = row[FEATURE_COLUMNS].to_frame().T
    X["node_id"] = X["node_id"].astype("category")

    out = {"node_id": node_id, "as_of": str(row["date"]), "theta_raw_today": float(row["theta_raw"])}
    for h in HORIZONS:
        model_path = os.path.join(OUTPUTS_DIR, f"model_h{h}.pkl")
        if not os.path.exists(model_path):
            continue
        with open(model_path, "rb") as f:
            fit = pickle.load(f)
        preds = {}
        for name, model in fit["models"].items():
            preds[name] = float(model.predict(X)[0])
        out[f"h{h}"] = {
            "predicted_change": preds["mean"],
            "predicted_level": out["theta_raw_today"] + preds["mean"],
            "interval": {
                f"q{a}": out["theta_raw_today"] + preds[f"q{a}"] for a in QUANTILE_ALPHAS if f"q{a}" in preds
            },
        }
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", type=int, default=None, help="Single node_id; default: all nodes in the cached feature table")
    args = parser.parse_args()

    table_path = os.path.join(OUTPUTS_DIR, "feature_table.parquet")
    if not os.path.exists(table_path):
        raise SystemExit("outputs/feature_table.parquet not found -- run `python train.py` first.")

    node_ids = [args.node] if args.node else sorted(pd.read_parquet(table_path)["node_id"].unique())
    for nid in node_ids:
        result = predict_node(int(nid))
        print(result)
