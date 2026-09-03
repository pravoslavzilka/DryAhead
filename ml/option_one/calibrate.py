"""Calibrate bucket-model parameters with differential evolution, scored by KGE.

Global optimization instead of gradient descent because Ks has a kink in it
(the piecewise readily-available-water threshold) -- the error surface is
non-convex and local optimizers land in whatever valley they started near.

Pooling strategy (see config.POOLED_PARAMS / PER_NODE_PARAMS): Kc and p are
vegetation properties and should be shared across nodes; theta_fc, theta_wp,
Zr, tau_d, runoff_frac (plus the two sensor-calibration transform params) are
site/sensor properties fit per node. Implemented as two stages rather than one
joint ~37-dimensional optimization: stage A fits every node fully
independently (Kc, p free) to get a per-node estimate of the vegetation
parameters, stage B pools Kc/p (median across nodes) and re-fits the
remaining per-node parameters with those pooled and fixed. This is
deliberately a simplification of a full joint fit -- documented in the
option_one README -- but keeps each optimization at a tractable ~9
dimensions and still respects "vegetation params shared, site params free".
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from bucket_model import BucketParams, simulate
from config import (
    ALL_PARAMS,
    BOUNDS,
    INVALID_PENALTY,
    MIN_SCORE_DAYS,
    MIN_TAW_GAP,
    MIN_VALIDATION_DAYS,
    PER_NODE_PARAMS,
    POOLED_PARAMS,
    SPINUP_DAYS,
)
from metrics import kge


def align_series(weather: pd.DataFrame, obs_proxy: pd.Series) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    """Continuous daily rain/et0 over weather's full range, plus obs values
    reindexed onto that same range (NaN where the node has no reading) so the
    simulation stays physically continuous through sensor gaps."""
    idx = weather.index
    obs_aligned = obs_proxy.reindex(idx).to_numpy(dtype=float)
    return idx, weather["rain_mm"].to_numpy(dtype=float), weather["et0_mm"].to_numpy(dtype=float), obs_aligned


def _build_params(values: dict[str, float]) -> BucketParams | None:
    if values["theta_fc"] - values["theta_wp"] < MIN_TAW_GAP:
        return None
    return BucketParams(
        theta_fc=values["theta_fc"],
        theta_wp=values["theta_wp"],
        Zr=values["Zr"],
        Kc=values["Kc"],
        p=values["p"],
        tau_d=values["tau_d"],
        runoff_frac=values["runoff_frac"],
    )


def _to_physical_theta(obs_proxy: np.ndarray, cal_a: float, cal_b: float) -> np.ndarray:
    return cal_a * obs_proxy + cal_b


def make_objective(
    rain: np.ndarray,
    et0: np.ndarray,
    obs_proxy: np.ndarray,
    names: list[str],
    fixed: dict[str, float] | None,
    fit_end_idx: int | None = None,
):
    """fit_end_idx restricts scoring to obs[:fit_end_idx] (the calibration
    slice) even though the simulation itself always runs the full series --
    this is what keeps the validation tail genuinely held out."""
    valid_mask = ~np.isnan(obs_proxy)
    spinup_mask = np.zeros(len(obs_proxy), dtype=bool)
    spinup_mask[SPINUP_DAYS:] = True
    score_mask = valid_mask & spinup_mask
    if fit_end_idx is not None:
        window_mask = np.zeros(len(obs_proxy), dtype=bool)
        window_mask[:fit_end_idx] = True
        score_mask &= window_mask

    def objective(x: np.ndarray) -> float:
        values = dict(zip(names, x))
        if fixed:
            values.update(fixed)

        params = _build_params(values)
        if params is None:
            return INVALID_PENALTY

        theta_sim = simulate(rain, et0, params)
        obs_theta = _to_physical_theta(obs_proxy, values["cal_a"], values["cal_b"])

        if score_mask.sum() < MIN_SCORE_DAYS:
            return INVALID_PENALTY

        score = kge(theta_sim[score_mask], obs_theta[score_mask])["kge"]
        if not np.isfinite(score):
            return INVALID_PENALTY
        return 1.0 - score

    return objective


def fit_node(
    rain: np.ndarray,
    et0: np.ndarray,
    obs_proxy: np.ndarray,
    fixed_shared: dict[str, float] | None = None,
    seed: int = 0,
    maxiter: int = 300,
    popsize: int = 20,
    fit_end_idx: int | None = None,
) -> dict:
    names = list(PER_NODE_PARAMS) + ([] if fixed_shared else list(POOLED_PARAMS))
    bounds = [BOUNDS[n] for n in names]
    objective = make_objective(rain, et0, obs_proxy, names, fixed_shared, fit_end_idx=fit_end_idx)

    result = differential_evolution(
        objective,
        bounds,
        seed=seed,
        maxiter=maxiter,
        popsize=popsize,
        tol=1e-7,
        mutation=(0.5, 1.5),
        recombination=0.7,
        polish=True,
        updating="deferred",
    )

    fitted = dict(zip(names, result.x))
    if fixed_shared:
        fitted.update(fixed_shared)

    converged = result.fun < INVALID_PENALTY / 2
    physically_valid = fitted["theta_fc"] - fitted["theta_wp"] >= MIN_TAW_GAP
    # When there's too little scorable data (see MIN_SCORE_DAYS), every
    # candidate the optimizer tries scores the same INVALID_PENALTY, so it
    # has no signal to prefer a valid theta_wp<theta_fc ordering and can
    # return whatever the population last held -- including an invalid one.
    # Callers must check `valid` before building a BucketParams from this.

    return {
        "params": {k: fitted[k] for k in ALL_PARAMS},
        "valid": bool(converged and physically_valid),
        "loss": float(result.fun),
        "kge": float(1.0 - result.fun) if converged else float("nan"),
        "success": bool(result.success),
        "nit": int(result.nit),
    }


def has_validation_coverage(obs_proxy: np.ndarray, fit_end_idx: int | None) -> bool:
    """Whether a node has enough obs *past* fit_end_idx to ever be cross-checked.
    A node that goes dead before validation starts can still calibrate fine
    in-sample (nothing stops an optimizer from fitting noise it's shown), but
    there's no way to tell whether that fit generalizes -- so it shouldn't
    get an equal vote in pool_shared alongside nodes that can be checked."""
    if fit_end_idx is None:
        return True  # no split configured -- can't apply this criterion
    return int(np.sum(~np.isnan(obs_proxy[fit_end_idx:]))) >= MIN_VALIDATION_DAYS


def pool_shared(node_fits: dict[int, dict]) -> dict[str, float]:
    """Median Kc/p across nodes' independent (stage-A) fits -- excluding any
    node whose stage-A fit never converged to a physically valid parameter
    set, so a data-starved node can't drag the shared vegetation parameters
    toward whatever arbitrary point its unconstrained optimizer landed on.
    Callers should pre-filter `node_fits` to nodes with validation coverage
    (see has_validation_coverage) before calling this -- see calibrate_all."""
    usable = {nid: fit for nid, fit in node_fits.items() if fit["valid"]} or node_fits
    return {
        name: float(np.median([fit["params"][name] for fit in usable.values()]))
        for name in POOLED_PARAMS
    }


def calibrate_all(
    node_data: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]],
    fit_end_idx: int | None = None,
    seed: int = 0,
    maxiter: int = 300,
    popsize: int = 20,
    pool_vegetation: bool = False,
) -> dict:
    """node_data: {node_id: (rain_mm, et0_mm, obs_theta_proxy)} all aligned to
    the same continuous daily index (NaN in obs_theta_proxy where missing).
    `fit_end_idx` is the calibration/validation split index (same for every
    node, since they share the date index) -- scoring never touches obs at or
    past this index, so validate.py's held-out metrics are leakage-free.

    `pool_vegetation` defaults to False: every node is fit fully independently
    (Kc/p included), and `final` is just `stage_a`. Kc/p are properties of
    *vegetation type*, not of the plot -- pooling them across nodes is only
    correct when the nodes genuinely sit under the same crop. Pass True only
    when you know that holds for this deployment; forcing a shared Kc/p
    across nodes under different vegetation doesn't average away the
    mismatch, it pushes it into theta_fc/theta_wp/Zr, corrupting the site
    parameters to compensate for a vegetation assumption that's wrong for
    part of the site.

    Returns {"stage_a": {node_id: fit}, "pooled_shared": {...} | None,
    "final": {node_id: fit}, "pooling_nodes": [node_id, ...]} -- the last two
    are stage_a-equivalent and [] when pool_vegetation is False.
    """
    stage_a = {
        node_id: fit_node(
            rain, et0, obs, fixed_shared=None, seed=seed + node_id, fit_end_idx=fit_end_idx,
            maxiter=maxiter, popsize=popsize,
        )
        for node_id, (rain, et0, obs) in node_data.items()
    }

    if not pool_vegetation:
        return {"stage_a": stage_a, "pooled_shared": None, "pooling_nodes": [], "final": stage_a}

    poolable = {
        node_id: fit
        for node_id, fit in stage_a.items()
        if has_validation_coverage(node_data[node_id][2], fit_end_idx)
    } or stage_a  # fall back to everyone if no node has validation coverage at all
    pooled = pool_shared(poolable)

    final = {
        node_id: fit_node(
            rain, et0, obs, fixed_shared=pooled, seed=seed + 100 + node_id, fit_end_idx=fit_end_idx,
            maxiter=maxiter, popsize=popsize,
        )
        for node_id, (rain, et0, obs) in node_data.items()
    }

    return {
        "stage_a": stage_a,
        "pooled_shared": pooled,
        "pooling_nodes": sorted(poolable.keys()),
        "final": final,
    }


def check_equifinality(
    rain: np.ndarray,
    et0: np.ndarray,
    obs_proxy: np.ndarray,
    fixed_shared: dict[str, float] | None = None,
    n_starts: int = 8,
    base_seed: int = 1000,
    maxiter: int = 300,
    popsize: int = 20,
) -> pd.DataFrame:
    """Refit from several random starts; parameters with coefficient of
    variation above ~0.2 aren't constrained by the data and shouldn't be
    quoted as measured soil properties."""
    names = list(PER_NODE_PARAMS) + ([] if fixed_shared else list(POOLED_PARAMS))
    runs = []
    for i in range(n_starts):
        fit = fit_node(
            rain, et0, obs_proxy, fixed_shared=fixed_shared, seed=base_seed + i,
            maxiter=maxiter, popsize=popsize,
        )
        runs.append(fit["params"])

    df = pd.DataFrame(runs)[names]
    summary = pd.DataFrame(
        {
            "mean": df.mean(),
            "std": df.std(),
            "cv": (df.std() / df.mean().abs()).abs(),
        }
    )
    summary["well_constrained"] = summary["cv"] < 0.2
    return summary
