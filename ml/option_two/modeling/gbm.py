"""LightGBM training: direct multi-horizon (one model per horizon, no
recursive rollout), mean + quantile objectives, expanding-window
chronological CV, and leave-one-node-out evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
    BACKEND = "lightgbm"
except ImportError:  # pragma: no cover - exercised only if lightgbm install fails
    from sklearn.ensemble import HistGradientBoostingRegressor
    BACKEND = "sklearn"

from config import CV_MIN_TRAIN_DAYS, CV_TEST_DAYS, EARLY_STOPPING_ROUNDS, GBM_PARAMS, QUANTILE_ALPHAS
from ingest.features import FEATURE_COLUMNS


@dataclass
class FoldResult:
    fold: int
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train: int
    n_test: int
    pred: np.ndarray
    obs: np.ndarray


def _prep_xy(table: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Rows with a non-null target for this horizon, X (categorical
    node_id) / y / the full row set (for date/node bookkeeping)."""
    target_col = f"target_h{horizon}"
    rows = table[table[target_col].notna()].copy()
    X = rows[FEATURE_COLUMNS].copy()
    X["node_id"] = X["node_id"].astype("category")
    y = rows[target_col]
    return X, y, rows


def _fit_one(X_train, y_train, X_val, y_val, objective: str, alpha: float | None = None):
    if BACKEND == "lightgbm":
        params = dict(GBM_PARAMS)
        params["objective"] = objective
        if alpha is not None:
            params["alpha"] = alpha
        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)] if X_val is not None else None,
            categorical_feature=["node_id"],
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)] if X_val is not None else None,
        )
        return model

    # sklearn fallback -- HistGradientBoostingRegressor doesn't take a
    # named "quantile alpha" the same way for the mean objective, and its
    # own early-stopping is internal (validation_fraction), so X_val/y_val
    # aren't used the same way here; documented in README as a fallback
    # limitation if this path is ever exercised.
    from sklearn.ensemble import HistGradientBoostingRegressor
    kwargs = dict(
        max_depth=GBM_PARAMS["max_depth"], learning_rate=GBM_PARAMS["learning_rate"],
        max_iter=GBM_PARAMS["n_estimators"], l2_regularization=GBM_PARAMS["lambda_l2"],
        min_samples_leaf=GBM_PARAMS["min_child_samples"], categorical_features=["node_id"],
    )
    if objective == "quantile":
        kwargs.update(loss="quantile", quantile=alpha)
    model = HistGradientBoostingRegressor(**kwargs)
    model.fit(X_train, y_train)
    return model


def expanding_window_cv(table: pd.DataFrame, horizon: int, min_train_days: int = CV_MIN_TRAIN_DAYS,
                         test_days: int = CV_TEST_DAYS) -> list[FoldResult]:
    """Chronological expanding-window CV: fold k trains on every row with
    date <= some cutoff and tests on the next `test_days` calendar days,
    cutoff advancing by test_days each fold. Never shuffled. A fold is
    skipped if it has no non-null-target rows."""
    X, y, rows = _prep_xy(table, horizon)
    dates = rows["date"]
    start, end = dates.min(), dates.max()

    folds: list[FoldResult] = []
    cutoff = start + pd.Timedelta(days=min_train_days)
    fold_idx = 0
    while cutoff < end:
        test_end = cutoff + pd.Timedelta(days=test_days)
        train_mask = dates <= cutoff
        test_mask = (dates > cutoff) & (dates <= test_end)
        n_train, n_test = train_mask.sum(), test_mask.sum()
        if n_train >= 20 and n_test >= 1:
            model = _fit_one(X[train_mask], y[train_mask], None, None, objective="regression")
            pred = np.asarray(model.predict(X[test_mask]))
            folds.append(FoldResult(
                fold=fold_idx, train_end=cutoff, test_start=cutoff + pd.Timedelta(days=1),
                test_end=test_end, n_train=int(n_train), n_test=int(n_test),
                pred=pred, obs=y[test_mask].to_numpy(),
            ))
            fold_idx += 1
        cutoff = test_end
    return folds


def leave_one_node_out(table: pd.DataFrame, horizon: int) -> dict[int, FoldResult]:
    """Train on every node except one, test on the held-out node. This is
    the honest test of generalization to a new site."""
    X, y, rows = _prep_xy(table, horizon)
    out: dict[int, FoldResult] = {}
    for node_id in sorted(rows["node_id"].unique()):
        train_mask = rows["node_id"] != node_id
        test_mask = ~train_mask
        if test_mask.sum() < 1 or train_mask.sum() < 20:
            continue
        model = _fit_one(X[train_mask], y[train_mask], None, None, objective="regression")
        pred = np.asarray(model.predict(X[test_mask]))
        out[node_id] = FoldResult(
            fold=-1, train_end=pd.NaT, test_start=pd.NaT, test_end=pd.NaT,
            n_train=int(train_mask.sum()), n_test=int(test_mask.sum()),
            pred=pred, obs=y[test_mask].to_numpy(),
        )
    return out


def fit_final_models(table: pd.DataFrame, horizon: int) -> dict:
    """Fit the mean model + quantile models at QUANTILE_ALPHAS on ALL
    available rows for this horizon (used for train.py's saved models /
    predict.py, not for evaluation -- evaluation is the CV/LONO functions
    above, which never touch these fits)."""
    X, y, rows = _prep_xy(table, horizon)
    # last 15% chronologically held out purely as an early-stopping monitor
    # for these final models -- not reported as a performance number
    # anywhere (that's what expanding_window_cv/leave_one_node_out are for).
    order = rows["date"].argsort()
    n = len(order)
    split = max(1, int(n * 0.85))
    tr_idx, val_idx = order[:split], order[split:]
    has_val = len(val_idx) >= 5

    models = {"mean": _fit_one(X.iloc[tr_idx], y.iloc[tr_idx],
                                X.iloc[val_idx] if has_val else None, y.iloc[val_idx] if has_val else None,
                                objective="regression")}
    for alpha in QUANTILE_ALPHAS:
        models[f"q{alpha}"] = _fit_one(X.iloc[tr_idx], y.iloc[tr_idx],
                                        X.iloc[val_idx] if has_val else None, y.iloc[val_idx] if has_val else None,
                                        objective="quantile", alpha=alpha)
    return {"horizon": horizon, "models": models, "n_rows": n, "feature_columns": list(FEATURE_COLUMNS)}
