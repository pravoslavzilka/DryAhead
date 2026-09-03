"""Synthetic data generator + self-test: build a dataset from known
parameters, run the full calibrate/validate pipeline against it, and check
whether the optimizer recovers the true parameters (it recovers behaviour,
not necessarily every individual parameter -- see check_equifinality).

Run directly: `python synthetic.py`
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bucket_model import BucketParams, simulate
from calibrate import check_equifinality, fit_node
from metrics import kge, persistence_forecast, rmse

TRUE_PARAMS = {
    "theta_fc": 0.320,
    "theta_wp": 0.130,
    "Zr": 700.0,
    "Kc": 0.950,
    "p": 0.500,
    "tau_d": 2.00,
    "runoff_frac": 0.120,
}
TRUE_CAL = {"cal_a": 0.35, "cal_b": 0.04}


def synthetic_weather(n_days: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic rain (intermittent, gamma-distributed on wet days) and a
    seasonal ET0 sinusoid -- enough structure to exercise runoff, drainage
    and the Ks kink without claiming to be real climate data."""
    rng = np.random.default_rng(seed)
    doy = np.arange(n_days) % 365

    wet_prob = 0.30 + 0.15 * np.sin(2 * np.pi * (doy - 60) / 365)  # wetter in spring
    is_wet = rng.random(n_days) < wet_prob
    rain = np.where(is_wet, rng.gamma(shape=1.5, scale=6.0, size=n_days), 0.0)

    et0_base = 2.5 + 2.3 * np.sin(2 * np.pi * (doy - 80) / 365)
    et0 = np.clip(et0_base + rng.normal(0, 0.3, n_days), 0.1, None)

    return rain, et0


def make_dataset(
    n_days: int = 730,
    true_params: dict = TRUE_PARAMS,
    true_cal: dict = TRUE_CAL,
    noise_std: float = 0.01,
    gap_frac: float = 0.08,
    seed: int = 0,
) -> dict:
    rng = np.random.default_rng(seed)
    rain, et0 = synthetic_weather(n_days, seed=seed)

    params = BucketParams(**true_params)
    theta_true = simulate(rain, et0, params, S0=true_params["theta_fc"])

    proxy = (theta_true - true_cal["cal_b"]) / true_cal["cal_a"]
    proxy = np.clip(proxy + rng.normal(0, noise_std, n_days), 0.0, 1.0)

    gaps = rng.random(n_days) < gap_frac
    obs_proxy = proxy.copy()
    obs_proxy[gaps] = np.nan

    return {"rain": rain, "et0": et0, "theta_true": theta_true, "obs_proxy": obs_proxy}


def run_self_test(n_days: int = 730, seed: int = 0, maxiter: int = 300, popsize: int = 20, n_equifinality_starts: int = 8) -> None:
    data = make_dataset(n_days=n_days, seed=seed)
    rain, et0, obs_proxy = data["rain"], data["et0"], data["obs_proxy"]

    fit_end_idx = int(n_days * 0.70)

    print("Fitting bucket model to synthetic data via differential evolution...", flush=True)
    fit = fit_node(rain, et0, obs_proxy, fixed_shared=None, seed=seed, fit_end_idx=fit_end_idx, maxiter=maxiter, popsize=popsize)

    print(f"\nCalibration KGE (fit slice only): {fit['kge']:.3f}")
    print(f"{'parameter':<14}{'fitted':>10}{'true':>10}")
    all_true = {**TRUE_PARAMS, **TRUE_CAL}
    for name, value in fit["params"].items():
        true_val = all_true.get(name)
        true_str = f"{true_val:.3f}" if true_val is not None else "n/a"
        print(f"{name:<14}{value:>10.3f}{true_str:>10}")

    # Held-out validation vs. persistence
    bucket_params = BucketParams(**{k: fit["params"][k] for k in TRUE_PARAMS})
    theta_sim = simulate(rain, et0, bucket_params)
    obs_theta = fit["params"]["cal_a"] * obs_proxy + fit["params"]["cal_b"]

    val_mask = np.zeros(n_days, dtype=bool)
    val_mask[fit_end_idx:] = True
    val_mask &= ~np.isnan(obs_theta)

    print(f"\nHeld-out validation ({val_mask.sum()} days):")
    print(f"  model       KGE={kge(theta_sim[val_mask], obs_theta[val_mask])['kge']:.3f}  "
          f"RMSE={rmse(theta_sim[val_mask], obs_theta[val_mask]):.4f}")

    val_idx = np.where(val_mask)[0]
    for h in (1, 3, 7, 14):
        pred, actual = persistence_forecast(obs_theta[val_idx], h)
        if len(actual) < 5:
            continue
        sim_pred = theta_sim[val_idx][: len(val_idx) - h]
        sim_actual = obs_theta[val_idx][h:]
        print(
            f"  {h:>2}d ahead  model RMSE={rmse(sim_pred, sim_actual):.4f}  "
            f"persistence RMSE={rmse(pred, actual):.4f}"
        )

    print(f"\nEquifinality check ({n_equifinality_starts} random-start refits; CV >= 0.2 means the data")
    print("doesn't constrain that parameter -- don't quote it as a measured property):")
    summary = check_equifinality(
        rain, et0, obs_proxy, fixed_shared=None, n_starts=n_equifinality_starts, base_seed=seed + 1000,
        maxiter=maxiter, popsize=popsize,
    )
    print(summary.round(3).to_string())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-days", type=int, default=730)
    parser.add_argument("--maxiter", type=int, default=300, help="Lower for a faster, less thorough smoke test.")
    parser.add_argument("--popsize", type=int, default=20)
    parser.add_argument("--equifinality-starts", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    run_self_test(
        n_days=args.n_days, seed=args.seed, maxiter=args.maxiter, popsize=args.popsize,
        n_equifinality_starts=args.equifinality_starts,
    )
