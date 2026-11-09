"""Step 5 -- validation, per node.

- Equifinality: refit from >=12 seeds, report mean/std/CV per parameter.
  CV above 0.2 means that parameter isn't constrained by the data.
- Hold-out: reserve one window, fit on the rest, simulate the held-out one
  forward from its own observed start, report error.
- Persistence benchmark ("reading stays where it is") at 3/7/14 days into
  each window.
- Stage check: observed loss rate / ET0 over time per window -- flat
  throughout means the window never reached the stressed phase and `p` is
  unidentifiable from it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model.calibrate import PARAM_ORDER, WindowData, calibrate_node, kge, simulate_all
from ..model.drydown import integrate_et0


def equifinality(windows: list[WindowData], n_seeds: int = 12) -> dict:
    """Refits from n_seeds random seeds; returns per-parameter mean/std/CV.
    A parameter with CV > 0.2 isn't constrained by this node's data --
    report it, don't quote a lone fitted value for it."""
    fits = [calibrate_node(windows, seed=s) for s in range(n_seeds)]
    per_param = {}
    for p in PARAM_ORDER:
        values = np.array([f["params"][p] for f in fits])
        mean = float(values.mean())
        std = float(values.std())
        per_param[p] = {"mean": mean, "std": std, "cv": (std / abs(mean)) if mean != 0 else float("inf")}
    kges = [f["kge"] for f in fits]
    return {"per_param": per_param, "kge_mean": float(np.mean(kges)), "kge_std": float(np.std(kges)), "fits": fits}


def holdout_validate(windows: list[WindowData], holdout_index: int, seed: int = 0) -> dict:
    """Fits on all windows except `holdout_index`, simulates that window
    forward from its own observed start with the fitted params, reports
    error against what was actually observed.

    Passes min_windows=2 to calibrate_node: a node with exactly 3 windows
    (calibrate_node's own default floor) would otherwise never be
    hold-out-validatable at all, since training on windows-minus-one from
    3 leaves 2. This trains hold-out's fit thinner than the spec's normal
    3-window bar -- accepted deliberately, on the user's call, rather than
    silently working around it -- see NIGHT_SUMMARY.md."""
    train = [w for i, w in enumerate(windows) if i != holdout_index]
    held = windows[holdout_index]
    fit = calibrate_node(train, seed=seed, min_windows=2)
    sim = simulate_all(fit["params"], [held])
    return {
        "params": fit["params"],
        "held_out_kge": kge(sim, held.observed),
        "held_out_rmse": float(np.sqrt(np.mean((sim - held.observed) ** 2))),
    }


def persistence_benchmark(windows: list[WindowData], horizons_days: tuple[int, ...] = (3, 7, 14)) -> dict:
    """'Reading stays where it is' baseline: predicted value at horizon h
    is the window's own start_value. Mean absolute error (raw counts),
    averaged over windows that run at least that long."""
    out = {}
    for h in horizons_days:
        target_offset = pd.Timedelta(days=h)
        errors = []
        for w in windows:
            target_time = w.times[0] + target_offset
            if w.times[-1] < target_time:
                continue
            idx = min(int(w.times.searchsorted(target_time)), len(w.observed) - 1)
            errors.append(abs(w.observed[idx] - w.observed[0]))
        out[h] = {"n_windows": len(errors), "mae_raw": float(np.mean(errors)) if errors else None}
    return out


def stage_check(windows: list[WindowData]) -> list[dict]:
    """Observed |loss rate| / ET0 rate over time, per window. Roughly
    flat throughout (low relative variance) means the window never
    reached the stressed (Ks < 1) phase, so `p` isn't identifiable from
    that window alone."""
    out = []
    for w in windows:
        dt_days = np.diff(w.times.values).astype("timedelta64[s]").astype(float) / 86400.0
        raw_rate = np.abs(np.diff(w.observed)) / np.where(dt_days == 0, np.nan, dt_days)
        et0_rate = np.array(
            [
                integrate_et0(w.hourly_et0, t0, t1) / max((t1 - t0).total_seconds() / 86400.0, 1e-9)
                for t0, t1 in zip(w.times[:-1], w.times[1:])
            ]
        )
        ratio = raw_rate / np.where(et0_rate == 0, np.nan, et0_rate)
        mean_ratio = np.nanmean(ratio)
        flat = bool(np.isnan(mean_ratio) or mean_ratio == 0 or np.nanstd(ratio) < 0.1 * abs(mean_ratio))
        out.append({"window_start": w.times[0], "window_end": w.times[-1], "ratio_series": ratio.tolist(), "flat": flat})
    return out
