"""Persistence baseline, and the FAO-56 bucket model as a second baseline
if importable read-only from ml/option_one (never modified)."""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

_OPTION_ONE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "option_one")
_BUCKET_MODEL_PATH = os.path.join(_OPTION_ONE_DIR, "bucket_model.py")
_FITTED_PARAMS_PATH = os.path.join(_OPTION_ONE_DIR, "outputs", "fitted_params.json")


def persistence_prediction(table: pd.DataFrame, horizon: int) -> pd.Series:
    """Persistence baseline for target_h{horizon}: predicts zero change
    ("moisture in h days = moisture today"), i.e. predicted target = 0.
    Returned aligned to `table`'s index so it can be compared row-for-row
    against the model's prediction on the same rows."""
    return pd.Series(0.0, index=table.index)


def water_balance_available() -> bool:
    """True if ml/option_one/bucket_model.py AND its already-fitted
    per-node parameters exist in this repo (read-only dependency, never
    imported at module scope so its absence doesn't break this package)."""
    return os.path.exists(_BUCKET_MODEL_PATH) and os.path.exists(_FITTED_PARAMS_PATH)


def _load_bucket_model():
    """Load ml/option_one/bucket_model.py by file path -- read-only, never
    modified, and not added to sys.path (avoids colliding with option_two's
    own top-level module names like `config`).

    Registered in sys.modules under a private name before exec_module: its
    @dataclass BucketParams needs cls.__module__ resolvable via
    sys.modules during class creation (dataclasses._is_type does this),
    which fails with an unhelpful AttributeError if the module isn't
    registered first."""
    import importlib.util
    import sys
    name = "_option_one_bucket_model"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _BUCKET_MODEL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_fitted_params() -> dict:
    with open(_FITTED_PARAMS_PATH, encoding="utf-8") as f:
        return json.load(f)["per_node"]


def water_balance_raw_series(node_id: int, weather: pd.DataFrame, air: float, water: float) -> pd.Series | None:
    """Run option_one's calibrated FAO-56 bucket model forward over
    `weather` (daily precipitation_sum/et0_fao_evapotranspiration, date
    index -- same per-node weather this pipeline already fetches, just not
    rolled up into features), and convert its theta output back into raw
    ADC units.

    This borrows two things that already exist in the repo, calibrated by
    option_one, not invented here: the per-node hardware calibration
    endpoints (air/water, from Supabase `sensor_calibration` -- real ADC
    readings taken in dry air and in water) and option_one's already-fit
    (cal_a, cal_b) linear map from the (air-raw)/(air-water) proxy to
    physical theta. Inverting that same map (raw = air - proxy*(air-water),
    proxy = (theta-cal_b)/cal_a) is a unit conversion for this baseline
    comparison only -- it is never written back into option_two's own
    features or target, which the brief requires stay raw-ADC, uncalibrated.

    Returns None if this node has no fitted params (shouldn't happen for
    the 5 nodes option_one has calibrated, but checked rather than assumed).
    """
    params_by_node = _load_fitted_params()
    p = params_by_node.get(str(node_id))
    if p is None:
        return None

    bm = _load_bucket_model()
    params = bm.BucketParams(
        theta_fc=p["theta_fc"], theta_wp=p["theta_wp"], Zr=p["Zr"],
        Kc=p["Kc"], p=p["p"], tau_d=p["tau_d"], runoff_frac=p["runoff_frac"],
    )
    rain = weather["precipitation_sum"].to_numpy(dtype=float)
    et0 = weather["et0_fao_evapotranspiration"].to_numpy(dtype=float)
    theta = bm.simulate(rain, et0, params)

    proxy = (theta - p["cal_b"]) / p["cal_a"]
    raw_equiv = air - proxy * (air - water)
    return pd.Series(raw_equiv, index=weather.index)


def add_water_balance_columns(table: pd.DataFrame, weather_by_node: dict[int, pd.DataFrame],
                               cal: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Add wb_pred_h{h} columns to `table` (NaN throughout if
    water_balance_available() is False, or for any node missing fitted
    params) -- the bucket-model analog of target_h{h}: predicted
    raw-ADC-equivalent change over each horizon, from a fixed, already-
    calibrated physical simulation, not fit on this table at all."""
    if not water_balance_available():
        for h in horizons:
            table[f"wb_pred_h{h}"] = np.nan
        return table

    frames = []
    for node_id, weather in weather_by_node.items():
        if node_id not in cal.index:
            continue
        air, water = float(cal.loc[node_id, "air"]), float(cal.loc[node_id, "water"])
        raw_equiv = water_balance_raw_series(node_id, weather, air, water)
        if raw_equiv is None:
            continue
        node_df = pd.DataFrame({"date": raw_equiv.index, "node_id": node_id})
        for h in horizons:
            node_df[f"wb_pred_h{h}"] = raw_equiv.shift(-h).to_numpy() - raw_equiv.to_numpy()
        frames.append(node_df)

    if not frames:
        for h in horizons:
            table[f"wb_pred_h{h}"] = np.nan
        return table

    wb = pd.concat(frames, ignore_index=True)
    merged = table.merge(wb, on=["date", "node_id"], how="left")
    merged.index = table.index
    return merged


# option_one/config.py's CALIBRATION_FRACTION (0.70) and run_pipeline.py's
# 35-day pre-buffer, both read directly from that source rather than
# guessed -- see water_balance_held_out_cutoff's docstring for why this
# matters here.
_WB_CALIBRATION_FRACTION = 0.70
_WB_CALIBRATION_LEAD_DAYS = 35


def water_balance_held_out_cutoff(table: pd.DataFrame) -> pd.Timestamp:
    """Reconstructs the single shared date after which option_one's bucket
    model was NOT allowed to see data during its own calibration (see
    option_one/run_pipeline.py: start = earliest obs date - 35d, end =
    latest obs date, fit_end_idx = int(n_days * CALIBRATION_FRACTION), all
    nodes split at that one shared date since the differential-evolution
    calibration runs once across every node with a common fit_end_idx).

    Why this matters: water_balance_raw_series simulates the bucket model
    forward over EVERY day in a node's weather range using parameters
    fit on the *first* 70% of the combined record. Scoring those
    predictions against target rows that fall before this cutoff is
    scoring the model on data it was fit to reproduce -- not a real
    generalization test, unlike persistence (fits nothing) or the GBM
    (proper CV/LONO). Only rows at or after this cutoff are a fair
    apples-to-apples comparison; see water_balance_metrics_for_fold's
    `min_date` parameter.

    Reconstructed (not read from an option_one output -- no run artifact
    stores the exact cutoff date) from `table`'s own overall date range,
    cross-checked against option_one/outputs/validation_report.json's
    n_val_days=28 for node 1 (whose own record ends 2026-09-02): this
    reconstruction gives 2026-08-05, i.e. 28 days before that, matching
    exactly.
    """
    start = table["date"].min() - pd.Timedelta(days=_WB_CALIBRATION_LEAD_DAYS)
    end = table["date"].max()
    n_days = (end - start).days + 1
    fit_end_idx = int(n_days * _WB_CALIBRATION_FRACTION)
    return start + pd.Timedelta(days=fit_end_idx)


def water_balance_metrics_for_fold(table: pd.DataFrame, horizon: int,
                                    test_dates: np.ndarray, test_node_ids: np.ndarray,
                                    min_date: pd.Timestamp | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Look up wb_pred_h{horizon} for exactly the (date, node_id) pairs a
    CV/LONO fold tested on (see gbm.FoldResult.test_dates/test_node_ids),
    and the matching observed target, dropping any row where the water
    balance has no prediction (missing fitted params, or a date outside its
    weather range). Returns (wb_pred, obs) ready for eval.metrics.all_metrics
    -- may be shorter than the fold's own pred/obs if coverage is partial;
    callers should report the count actually used."""
    col = f"wb_pred_h{horizon}"
    target_col = f"target_h{horizon}"
    key = pd.DataFrame({"date": test_dates, "node_id": test_node_ids})
    looked_up = key.merge(
        table[["date", "node_id", col, target_col]].drop_duplicates(["date", "node_id"]),
        on=["date", "node_id"], how="left",
    )
    valid = looked_up[col].notna() & looked_up[target_col].notna()
    if min_date is not None:
        valid &= looked_up["date"] >= min_date
    return looked_up.loc[valid, col].to_numpy(), looked_up.loc[valid, target_col].to_numpy()
