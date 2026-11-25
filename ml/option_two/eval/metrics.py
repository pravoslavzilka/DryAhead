"""Goodness-of-fit metrics, independent implementation (same standard
formulas as ml/option_one/metrics.py, not imported from it)."""

from __future__ import annotations

import numpy as np


def rmse(pred: np.ndarray, obs: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - obs) ** 2)))


def mae(pred: np.ndarray, obs: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - obs)))


def nse(pred: np.ndarray, obs: np.ndarray) -> float:
    """Nash-Sutcliffe efficiency. 1 = perfect, 0 = as good as predicting the
    observed mean every time, <0 worse than that."""
    denom = np.sum((obs - obs.mean()) ** 2)
    if denom == 0:
        return float("nan")
    return float(1 - np.sum((pred - obs) ** 2) / denom)


def kge(pred: np.ndarray, obs: np.ndarray) -> dict[str, float]:
    """Kling-Gupta Efficiency, decomposed: KGE = 1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2).

    r (Pearson correlation) is undefined when either series has zero
    variance -- notably the persistence baseline here, which always
    predicts exactly 0 change, so np.corrcoef(pred, obs) would divide by
    a zero pred-std. Reported as NaN explicitly rather than left to trigger
    a runtime warning and an implicit NaN from numpy.
    """
    obs_std = obs.std()
    obs_mean = obs.mean()
    pred_std = pred.std()
    if obs_std == 0 or obs_mean == 0 or len(obs) < 2:
        return {"kge": float("nan"), "r": float("nan"), "alpha": float("nan"), "beta": float("nan")}
    if pred_std == 0:
        r = float("nan")
    else:
        r = float(np.corrcoef(pred, obs)[0, 1])
    alpha = float(pred.std() / obs_std)
    beta = float(pred.mean() / obs_mean)
    value = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
    return {"kge": float(value), "r": r, "alpha": alpha, "beta": beta}


def all_metrics(pred: np.ndarray, obs: np.ndarray) -> dict[str, float]:
    out = {"rmse": rmse(pred, obs), "mae": mae(pred, obs), "nse": nse(pred, obs)}
    out.update(kge(pred, obs))
    return out
