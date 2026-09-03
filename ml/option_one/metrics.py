"""Goodness-of-fit metrics for daily theta series."""

from __future__ import annotations

import numpy as np


def rmse(sim: np.ndarray, obs: np.ndarray) -> float:
    return float(np.sqrt(np.mean((sim - obs) ** 2)))


def nse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Nash-Sutcliffe efficiency. 1 = perfect, 0 = as good as the mean, <0 worse."""
    denom = np.sum((obs - obs.mean()) ** 2)
    if denom == 0:
        return float("nan")
    return float(1 - np.sum((sim - obs) ** 2) / denom)


def kge(sim: np.ndarray, obs: np.ndarray) -> dict[str, float]:
    """Kling-Gupta Efficiency, decomposed into its three components.

    KGE = 1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2)
      r     -- Pearson correlation (timing/shape)
      alpha -- std(sim)/std(obs) (variability ratio)
      beta  -- mean(sim)/mean(obs) (bias ratio)
    """
    obs_std = obs.std()
    obs_mean = obs.mean()
    if obs_std == 0 or obs_mean == 0 or len(obs) < 2:
        return {"kge": float("nan"), "r": float("nan"), "alpha": float("nan"), "beta": float("nan")}

    r = float(np.corrcoef(sim, obs)[0, 1])
    alpha = float(sim.std() / obs_std)
    beta = float(sim.mean() / obs_mean)
    value = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
    return {"kge": float(value), "r": r, "alpha": alpha, "beta": beta}


def persistence_forecast(obs: np.ndarray, horizon_days: int) -> tuple[np.ndarray, np.ndarray]:
    """Naive baseline: predicted[t] = obs[t - horizon_days]. Returns (pred, actual) aligned pairs."""
    if horizon_days >= len(obs):
        return np.array([]), np.array([])
    pred = obs[: len(obs) - horizon_days]
    actual = obs[horizon_days:]
    return pred, actual
