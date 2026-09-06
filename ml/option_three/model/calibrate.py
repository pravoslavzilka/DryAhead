"""Step 4/5 -- joint multi-window calibration, one node at a time.

Fits wet_ref, dry_ref (raw counts), Kc, p, and a mm-to-raw-counts scale
factor by minimizing 1 - KGE over all of a node's windows concatenated,
each window simulated forward from its own observed starting value (never
from a shared reference state) -- long windows pin dry_ref/p, short ones
pin Kc, per the task spec. Uses differential_evolution (global) because
the Ks kink (model.drydown.ks) breaks gradient-based optimizers.

Strictly one node at a time -- no pooling, no shared parameters, no
cross-node averaging (task spec, "Scope -- firm").
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from ..configs import site
from .drydown import simulate_window

BOUNDS = {
    "wet_ref": (float(site.ADC_MIN), float(site.ADC_MAX)),
    "dry_ref": (float(site.ADC_MIN), float(site.ADC_MAX)),
    "Kc": (0.1, 1.5),
    "p": (0.1, 0.9),
    # mm-to-raw-counts scale: unvalidated bound, not tuned against live
    # data this session -- see NIGHT_SUMMARY.md. Loosen/tighten once a
    # real fit shows whether the optimizer presses against it.
    "scale_mm_to_raw": (0.1, 300.0),
}
PARAM_ORDER = ("wet_ref", "dry_ref", "Kc", "p", "scale_mm_to_raw")


@dataclass
class WindowData:
    """One drying window's simulation inputs: timestamps, the observed raw
    series aligned to those timestamps (observed[0] is the window's own
    starting value), the hourly ET0 series covering the window (kept for
    eval/validate.py's stage_check), and et0_intervals -- ET0 (mm) for
    each consecutive pair of `times`, precomputed once via
    model.drydown.precompute_et0_intervals since it's parameter-
    independent and simulate_window is called tens of thousands of times
    per fit (see precompute_et0_intervals's docstring)."""

    times: pd.DatetimeIndex
    observed: np.ndarray
    hourly_et0: pd.Series
    et0_intervals: np.ndarray


def kge(sim: np.ndarray, obs: np.ndarray) -> float:
    """Kling-Gupta efficiency."""
    if np.std(obs) == 0 or np.std(sim) == 0:
        return -1e6
    r = float(np.corrcoef(sim, obs)[0, 1])
    alpha = float(np.std(sim) / np.std(obs))
    beta = float(np.mean(sim) / np.mean(obs))
    return 1.0 - float(np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))


def simulate_all(params: dict, windows: list[WindowData]) -> np.ndarray:
    sims = [
        simulate_window(
            w.times,
            w.observed[0],
            params["wet_ref"],
            params["dry_ref"],
            params["Kc"],
            params["p"],
            params["scale_mm_to_raw"],
            w.et0_intervals,
        )
        for w in windows
    ]
    return np.concatenate(sims)


def make_objective(windows: list[WindowData]):
    observed_concat = np.concatenate([w.observed for w in windows])

    def objective(x: np.ndarray) -> float:
        params = dict(zip(PARAM_ORDER, x))
        if params["dry_ref"] == params["wet_ref"]:
            return 1e6
        sim = simulate_all(params, windows)
        score = kge(sim, observed_concat)
        return 1.0 - score if np.isfinite(score) else 1e6

    return objective


def calibrate_node(windows: list[WindowData], seed: int = 0, min_windows: int = 3, **de_kwargs) -> dict:
    """Fits one node's parameters jointly across all its windows. Returns
    {"params": {...}, "kge": float, "seed": seed}.

    min_windows defaults to 3, the task spec's own floor for calibrating a
    node at all. eval/validate.holdout_validate passes min_windows=2: it
    trains on windows-minus-one, so a node with exactly 3 windows (the
    floor) would otherwise never be hold-out-validatable at all. The
    standalone 3-window floor for real (non-hold-out) calibration is
    unchanged -- only hold-out's internal training fit is allowed to run
    thinner than that, on the user's explicit call, at the cost of a
    weaker fit than the spec's own bar."""
    if len(windows) < min_windows:
        raise ValueError(f"need at least {min_windows} usable windows to calibrate, got {len(windows)}")
    objective = make_objective(windows)
    bounds = [BOUNDS[p] for p in PARAM_ORDER]
    result = differential_evolution(objective, bounds, seed=seed, polish=True, tol=1e-6, maxiter=500, **de_kwargs)
    params = dict(zip(PARAM_ORDER, result.x))
    return {"params": params, "kge": 1.0 - float(result.fun), "seed": seed}
