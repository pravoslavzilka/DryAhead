"""Ensemble forecast: run the calibrated bucket model once per weather
ensemble member, starting from the latest observed state. The spread across
members is a genuine probability distribution over next month's soil-water
state -- no ML involved, just the same physical model driven by 40-50
plausible futures instead of one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bucket_model import BucketParams, simulate
from config import MIN_TAW_GAP


def awf(theta: np.ndarray, theta_fc: float, theta_wp: float) -> np.ndarray:
    """Available Water Fraction: 1.0 at field capacity, 0.0 at wilting point."""
    return (theta - theta_wp) / (theta_fc - theta_wp)


def forecast_node(
    params: dict,
    current_theta: float,
    ensemble_rain: pd.DataFrame,
    ensemble_et0: pd.DataFrame,
) -> pd.DataFrame:
    """current_theta: latest physically-calibrated theta observation (already
    cal_a/cal_b transformed), used as the starting state S0.

    Returns a DataFrame of theta trajectories, one column per ensemble
    member, indexed by forecast date. Empty if `params` never converged to a
    physically valid fit (theta_fc - theta_wp >= config.MIN_TAW_GAP) -- see
    calibrate.fit_node's `valid` flag.
    """
    if params.get("theta_fc", 0) - params.get("theta_wp", 0) < MIN_TAW_GAP:
        return pd.DataFrame()

    bucket_params = BucketParams(
        theta_fc=params["theta_fc"],
        theta_wp=params["theta_wp"],
        Zr=params["Zr"],
        Kc=params["Kc"],
        p=params["p"],
        tau_d=params["tau_d"],
        runoff_frac=params["runoff_frac"],
    )

    members = ensemble_rain.columns.intersection(ensemble_et0.columns)
    trajectories = {}
    for member in members:
        rain = ensemble_rain[member].to_numpy(dtype=float)
        et0 = ensemble_et0[member].to_numpy(dtype=float)
        valid = ~(np.isnan(rain) | np.isnan(et0))
        if valid.sum() == 0:
            continue
        theta_sim = simulate(rain[valid], et0[valid], bucket_params, S0=current_theta)
        trajectories[member] = pd.Series(theta_sim, index=ensemble_rain.index[valid])

    return pd.DataFrame(trajectories)


def summarize_forecast(theta_trajectories: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Per-date summary: theta and AWF quantiles across ensemble members --
    the product a parametric drought product would actually consume."""
    awf_trajectories = theta_trajectories.apply(
        lambda col: awf(col.to_numpy(), params["theta_fc"], params["theta_wp"])
    )
    summary = pd.DataFrame(
        {
            "theta_p10": theta_trajectories.quantile(0.10, axis=1),
            "theta_p50": theta_trajectories.quantile(0.50, axis=1),
            "theta_p90": theta_trajectories.quantile(0.90, axis=1),
            "awf_p10": awf_trajectories.quantile(0.10, axis=1),
            "awf_p50": awf_trajectories.quantile(0.50, axis=1),
            "awf_p90": awf_trajectories.quantile(0.90, axis=1),
            "prob_below_wilting": (theta_trajectories.le(params["theta_wp"])).mean(axis=1),
        }
    )
    return summary
