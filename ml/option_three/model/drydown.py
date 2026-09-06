"""Step 4 -- single-store water balance, raw sensor units, integrated over
real (uneven) elapsed time. No infiltration/runoff term -- drying windows
never contain rain (see events/windows.py).

Sign-agnostic by construction: `wet_ref`/`dry_ref` are fitted raw-count
references, and the drying direction is derived from their relative order
rather than passed in separately, so whichever empirical sign convention
events.windows.detect_sign_convention finds for a node, a consistent fit
of wet_ref/dry_ref reproduces it automatically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ks(depletion: float, span: float, p: float) -> float:
    """Water-stress coefficient.

    depletion: how far (raw counts) the level has already dried from
    wet_ref. span: the total wet-to-dry raw-count range,
    abs(dry_ref - wet_ref). p: readily-available-water depletion fraction.
    Ks = 1 while depletion <= p * span, then declines linearly to 0 at
    depletion = span (and stays 0 beyond, i.e. never over-dries)."""
    raw_thresh = p * span
    if depletion <= raw_thresh:
        return 1.0
    denom = span - raw_thresh
    if denom <= 0:
        return 0.0
    return float(np.clip((span - depletion) / denom, 0.0, 1.0))


def integrate_et0(hourly_et0: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """mm of ET0 between `start` and `end`, prorating partial hours from
    the hourly series (indexed by hour-start, UTC)."""
    if end <= start:
        return 0.0
    hours = hourly_et0.index
    lo = hours.searchsorted(start.floor("h"))
    hi = hours.searchsorted(end.floor("h"), side="right")
    total = 0.0
    for h in hours[lo:hi]:
        bucket_start, bucket_end = h, h + pd.Timedelta(hours=1)
        overlap_start = max(bucket_start, start)
        overlap_end = min(bucket_end, end)
        if overlap_end <= overlap_start:
            continue
        frac = (overlap_end - overlap_start).total_seconds() / 3600.0
        total += float(hourly_et0.loc[h]) * frac
    return total


def precompute_et0_intervals(times: pd.DatetimeIndex, hourly_et0: pd.Series) -> np.ndarray:
    """ET0 (mm) between each consecutive pair of `times`, length
    len(times)-1. Depends only on `times`/`hourly_et0`, never on fitted
    parameters -- compute once per window and reuse across every DE
    candidate, rather than recomputing it from scratch inside
    simulate_window on every objective evaluation (verified: that
    redundant recomputation was the dominant cost of a fit -- ~1.2s per
    single objective evaluation on real data, which multiplied out by
    differential_evolution's default popsize*ndim*maxiter made a single
    calibrate_node call take on the order of hours instead of seconds)."""
    return np.array(
        [integrate_et0(hourly_et0, t0, t1) for t0, t1 in zip(times[:-1], times[1:])],
        dtype=float,
    )


def simulate_window(
    times: pd.DatetimeIndex,
    start_value: float,
    wet_ref: float,
    dry_ref: float,
    kc: float,
    p: float,
    scale_mm_to_raw: float,
    et0_intervals: np.ndarray,
) -> np.ndarray:
    """Simulates raw level at each timestamp in `times`. times[0] is the
    window's own observed starting value (start_value) -- never wet_ref --
    per the task spec: each window is simulated forward from its own
    observed start, so long windows pin dry_ref/p while short ones pin Kc.

    `et0_intervals`: precomputed via precompute_et0_intervals -- ET0 (mm)
    for each of the len(times)-1 consecutive intervals. Parameter-
    independent, so the caller computes it once per window and passes it
    in, rather than this function re-deriving it from the raw hourly
    series on every call (see precompute_et0_intervals's docstring)."""
    span = abs(dry_ref - wet_ref)
    direction = 1.0 if dry_ref >= wet_ref else -1.0
    level = start_value
    out = np.empty(len(times))
    out[0] = level
    for i in range(1, len(times)):
        depletion = abs(level - wet_ref)
        k = ks(depletion, span, p)
        loss_raw = k * kc * et0_intervals[i - 1] * scale_mm_to_raw
        level = level + direction * loss_raw
        out[i] = level
    return out
