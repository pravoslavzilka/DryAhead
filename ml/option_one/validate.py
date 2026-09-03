"""Held-out validation: model vs. persistence, on the chronological tail
never touched by the calibration objective. Persistence (tomorrow = today) is
a genuinely hard baseline for soil moisture given how much memory it has --
the bar is "clearly beats persistence at 7+ days", not "beats it at all".
"""

from __future__ import annotations

import numpy as np

from bucket_model import BucketParams, simulate
from config import MIN_TAW_GAP, MIN_VALIDATION_DAYS, SPINUP_DAYS
from metrics import kge, persistence_forecast, rmse

HORIZONS_DAYS = (1, 3, 7, 14)


def validate_node(
    rain: np.ndarray,
    et0: np.ndarray,
    obs_proxy: np.ndarray,
    params: dict,
    fit_end_idx: int,
) -> dict:
    if params.get("theta_fc", 0) - params.get("theta_wp", 0) < MIN_TAW_GAP:
        return {
            "note": (
                "calibration did not converge to a physically valid parameter set "
                "(theta_fc - theta_wp below config.MIN_TAW_GAP) -- almost always means "
                "too little scorable data in the calibration window (see "
                "config.MIN_SCORE_DAYS); nothing to validate."
            )
        }

    bucket_params = BucketParams(
        theta_fc=params["theta_fc"],
        theta_wp=params["theta_wp"],
        Zr=params["Zr"],
        Kc=params["Kc"],
        p=params["p"],
        tau_d=params["tau_d"],
        runoff_frac=params["runoff_frac"],
    )
    theta_sim = simulate(rain, et0, bucket_params)
    obs_theta = params["cal_a"] * obs_proxy + params["cal_b"]

    val_mask = np.zeros(len(obs_proxy), dtype=bool)
    val_start = max(fit_end_idx, SPINUP_DAYS)
    val_mask[val_start:] = True
    val_mask &= ~np.isnan(obs_theta)

    if val_mask.sum() < MIN_VALIDATION_DAYS:
        return {"n_val_days": int(val_mask.sum()), "note": "too few held-out observations to score"}

    sim_val = theta_sim[val_mask]
    obs_val = obs_theta[val_mask]

    result = {
        "n_val_days": int(val_mask.sum()),
        "model": {**kge(sim_val, obs_val), "rmse": rmse(sim_val, obs_val)},
        "persistence_by_horizon": {},
        "model_by_horizon": {},
    }

    # Dense (gap-free) obs subsequence for persistence + horizon comparisons --
    # persistence needs obs[t-h] and obs[t] both present, and sim is dense by
    # construction so we align it onto the same dense obs index.
    val_idx = np.where(val_mask)[0]
    for h in HORIZONS_DAYS:
        pred, actual = persistence_forecast(obs_theta[val_idx], h)
        if len(actual) < 5:
            continue
        result["persistence_by_horizon"][h] = {**kge(pred, actual), "rmse": rmse(pred, actual)}

        sim_pred = theta_sim[val_idx][: len(val_idx) - h]
        sim_actual = obs_theta[val_idx][h:]
        result["model_by_horizon"][h] = {**kge(sim_pred, sim_actual), "rmse": rmse(sim_pred, sim_actual)}

    return result
