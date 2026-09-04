"""Evaluation orchestration: runs CV + leave-one-node-out per horizon,
compares against persistence, counts effective independent events, and
saves scatter/timeseries/SHAP plots + a markdown results summary.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from eval import baselines, metrics
from modeling import gbm


def effective_event_count(table: pd.DataFrame) -> dict[int, int]:
    """Count of independent wetting events per node: a transition from a
    dry run (days_since_rain > 0, or the very first row) into a rain day
    (precipitation_sum > RAIN_THRESHOLD_MM), i.e. the number of times
    `days_since_rain` resets to 0 after having been > 0. This is a simple,
    stated-in-the-open proxy for "distinct drydown cycles" -- not a
    hydrological event-separation algorithm -- chosen because it's easily
    auditable directly from days_since_rain, which is already a feature
    in the table.
    """
    out: dict[int, int] = {}
    for node_id, g in table.sort_values("date").groupby("node_id"):
        dsr = g["days_since_rain"].to_numpy()
        is_rain_day = np.concatenate([[False], dsr[1:] == 0])  # dsr==0 means today is a rain day
        # an "event start" is a rain day immediately following a day with
        # dsr > 0 (i.e. it had been dry) -- the first-ever rain day in the
        # record also counts as one event start.
        prev_dry_or_start = np.concatenate([[True], dsr[:-1] > 0])
        events = is_rain_day & prev_dry_or_start
        out[int(node_id)] = int(np.nansum(events))
    return out


def evaluate_horizon(table: pd.DataFrame, horizon: int) -> dict:
    cv_folds = gbm.expanding_window_cv(table, horizon)
    lono = gbm.leave_one_node_out(table, horizon)

    cv_pred = np.concatenate([f.pred for f in cv_folds]) if cv_folds else np.array([])
    cv_obs = np.concatenate([f.obs for f in cv_folds]) if cv_folds else np.array([])
    lono_pred = np.concatenate([f.pred for f in lono.values()]) if lono else np.array([])
    lono_obs = np.concatenate([f.obs for f in lono.values()]) if lono else np.array([])

    result = {"horizon": horizon, "n_cv_folds": len(cv_folds), "n_lono_nodes": len(lono)}

    if len(cv_obs):
        result["cv_model"] = metrics.all_metrics(cv_pred, cv_obs)
        persist_pred = np.zeros_like(cv_obs)
        result["cv_persistence"] = metrics.all_metrics(persist_pred, cv_obs)
        result["cv_pred"], result["cv_obs"] = cv_pred, cv_obs
    if len(lono_obs):
        result["lono_model"] = metrics.all_metrics(lono_pred, lono_obs)
        persist_pred = np.zeros_like(lono_obs)
        result["lono_persistence"] = metrics.all_metrics(persist_pred, lono_obs)
        result["lono_pred"], result["lono_obs"] = lono_pred, lono_obs

    # Water balance (option_one's fitted bucket model): scored on exactly
    # the same held-out rows as the GBM/persistence numbers above, via each
    # fold's test_dates/test_node_ids, not on the full table -- otherwise
    # it wouldn't be a fair side-by-side comparison. Coverage can be a
    # strict subset of n_cv/n_lono if a row's date falls outside the
    # bucket model's weather range or a node has no fitted params; that
    # count is reported alongside the metrics rather than silently
    # letting a smaller n produce a misleadingly different-looking result.
    #
    # Reported in two forms: "all" (every row with wb coverage, whether or
    # not that date was inside the bucket model's own calibration window)
    # and "held_out" (restricted to dates after
    # baselines.water_balance_held_out_cutoff -- see that function's
    # docstring for why the unrestricted number alone would overstate the
    # bucket model's generalization, unlike persistence/the GBM which have
    # no such in-sample overlap). held_out is the fair one to headline.
    if f"wb_pred_h{horizon}" in table.columns:
        cutoff = baselines.water_balance_held_out_cutoff(table)
        for prefix, fold_iterable in (("cv", cv_folds), ("lono", lono.values())):
            if not fold_iterable:
                continue
            for suffix, min_date in (("all", None), ("held_out", cutoff)):
                wb_pred, wb_obs = [], []
                for f in fold_iterable:
                    p, o = baselines.water_balance_metrics_for_fold(
                        table, horizon, f.test_dates, f.test_node_ids, min_date=min_date)
                    wb_pred.append(p); wb_obs.append(o)
                wb_pred_arr = np.concatenate(wb_pred) if wb_pred else np.array([])
                wb_obs_arr = np.concatenate(wb_obs) if wb_obs else np.array([])
                if len(wb_obs_arr):
                    key = f"{prefix}_water_balance" if suffix == "held_out" else f"{prefix}_water_balance_{suffix}"
                    result[key] = metrics.all_metrics(wb_pred_arr, wb_obs_arr)
                    result[f"{key}_n"] = len(wb_obs_arr)
        result["water_balance_held_out_cutoff"] = cutoff

    return result


def save_scatter_plot(pred: np.ndarray, obs: np.ndarray, horizon: int, path: str) -> None:
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(obs, pred, alpha=0.6, s=20)
    lim = [min(obs.min(), pred.min()), max(obs.max(), pred.max())]
    ax.plot(lim, lim, "k--", linewidth=1, label="perfect")
    ax.set_xlabel("Observed change in raw ADC units")
    ax.set_ylabel("Predicted change in raw ADC units")
    ax.set_title(f"h={horizon}d: predicted vs observed change (CV folds)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_timeseries_plot(dates: pd.Series, pred: np.ndarray, obs: np.ndarray, horizon: int, path: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    order = np.argsort(dates.to_numpy())
    ax.plot(dates.to_numpy()[order], obs[order], "o-", label="observed", markersize=3)
    ax.plot(dates.to_numpy()[order], pred[order], "o-", label="predicted", markersize=3)
    ax.set_ylabel("Change in raw ADC units")
    ax.set_title(f"h={horizon}d: predicted vs observed over held-out CV windows")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_shap_plot(table: pd.DataFrame, horizon: int, path: str) -> dict:
    """SHAP summary for the final mean model at this horizon. Returns the
    mean |SHAP| per feature so callers can report the top drivers in text,
    not just as a plot."""
    import shap
    from ingest.features import FEATURE_COLUMNS

    fit = gbm.fit_final_models(table, horizon)
    model = fit["models"]["mean"]
    X, y, rows = gbm._prep_xy(table, horizon)
    if len(X) < 10:
        return {}

    # Keep node_id as the same pandas "category" dtype the model was
    # trained with -- LightGBM's booster remembers which columns were
    # declared categorical at fit time and raises on a dtype mismatch
    # (e.g. converting to .cat.codes/int here) at predict time, which
    # pred_contrib (what TreeExplainer uses under the hood) also goes
    # through.
    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(X)

    # shap.summary_plot needs numeric data to color points by feature value;
    # node_id's category codes stand in for that here (only for the plot,
    # not for the SHAP values themselves, which were computed above).
    X_plot = X.copy()
    X_plot["node_id"] = X_plot["node_id"].cat.codes

    fig = plt.figure(figsize=(7, 6))
    shap.summary_plot(sv, X_plot, feature_names=FEATURE_COLUMNS, show=False, plot_size=None)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)

    mean_abs = np.abs(sv).mean(axis=0)
    importance = dict(sorted(zip(FEATURE_COLUMNS, mean_abs), key=lambda kv: -kv[1]))
    return importance
