"""Persistence baseline, and the FAO-56 bucket model as a second baseline
if importable read-only from ml/option_one (never modified)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def persistence_prediction(table: pd.DataFrame, horizon: int) -> pd.Series:
    """Persistence baseline for target_h{horizon}: predicts zero change
    ("moisture in h days = moisture today"), i.e. predicted target = 0.
    Returned aligned to `table`'s index so it can be compared row-for-row
    against the model's prediction on the same rows."""
    return pd.Series(0.0, index=table.index)


def water_balance_available() -> bool:
    """True if ml/option_one/bucket_model.py exists in this repo (read-only
    dependency, never imported at module scope so its absence doesn't break
    this package)."""
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "option_one", "bucket_model.py")
    return os.path.exists(path)
