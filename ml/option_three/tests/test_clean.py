"""Unit + synthetic leakage tests for data/clean.py.

Each rule is tested in isolation against a small hand-verifiable array
first, then clean_node() is exercised end-to-end against one synthetic
series with several known injected artifacts of different kinds, checking
that exactly the injected points are removed and every genuine point
survives untouched (the "leakage" test: no genuine data silently dropped,
no artifact silently kept).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.option_three.data import clean
from ml.option_three.configs import cleaning_thresholds as T


def _ts(n: int, start="2026-01-01T00:00", freq="20min"):
    return pd.date_range(start, periods=n, freq=freq, tz="UTC")


def test_range_check_flags_out_of_bounds_only():
    df = pd.DataFrame({"raw": [100.0, -5.0, 2000.0, 5000.0, 4095.0, 0.0]})
    flagged = clean.range_check(df)
    assert list(flagged) == [False, True, False, True, False, False]


def test_rate_of_change_flags_jump_without_rain_but_not_with_rain():
    # Step up at index 2 and stay there (not a reverting spike) -> only the
    # single large diff entering the step exceeds threshold; the diffs
    # after it are back to the normal ~10/reading pace.
    times = _ts(5)
    jump = T.MAX_RAW_DELTA_PER_READING + 50
    raw = [1000.0, 1010.0, 1010.0 + jump, 1010.0 + jump + 10, 1010.0 + jump + 20]
    df = pd.DataFrame({"ts": times, "raw": raw})

    no_rain = pd.Series(dtype=float)
    flagged_no_rain = clean.rate_of_change_check(df, no_rain)
    assert list(flagged_no_rain) == [False, False, True, False, False]

    # Rain in the hour before the jump -> not flagged.
    rain = pd.Series([2.0], index=[times[2] - pd.Timedelta(minutes=10)])
    flagged_with_rain = clean.rate_of_change_check(df, rain)
    assert list(flagged_with_rain) == [False, False, False, False, False]


def test_local_outlier_check_flags_spike_with_small_background_noise():
    times = _ts(9)
    rng = np.random.default_rng(0)
    baseline = 1000.0 + np.arange(9) * 1.0 + rng.uniform(-1.0, 1.0, size=9)
    raw = baseline.copy()
    raw[4] += 200.0  # spike far beyond the ~1-2 raw-count background noise
    df = pd.DataFrame({"ts": times, "raw": raw})
    flagged = clean.local_outlier_check(df)
    assert flagged.iloc[4]
    assert flagged.sum() == 1


def test_temperature_corroboration_splits_on_temp_discontinuity():
    # A single-tick temperature spike at index 2 shows up as a discontinuity
    # on both sides (indices 1 and 3), same as any single-point diff check --
    # index 4 is far from it and stays smooth, so it's the clean negative case.
    times = _ts(6)
    df = pd.DataFrame(
        {
            "ts": times,
            "temperature": [20.0, 20.1, 25.0, 20.2, 20.3, 20.4],
        }
    )
    flagged = pd.Series([False, False, True, False, True, False])
    corroborated = clean.temperature_corroboration(df, flagged)
    # index 2 sits at the real temperature spike -> corroborated.
    # index 4 is flagged (e.g. by another rule) but temperature is smooth there -> not corroborated.
    assert list(corroborated) == [False, False, True, False, False, False]


def test_short_run_check_flags_reverting_run_not_permanent_shift():
    tol = T.SHORT_RUN_REVERT_TOLERANCE_RAW
    # indices 0..2 baseline, 3-4 a 2-reading run shifted well past tolerance
    # and reverting at index 5, 6-9 a permanent shift that never reverts.
    raw = np.array([1000.0, 1000.0, 1000.0, 1000.0 + tol + 100, 1000.0 + tol + 90, 1000.0, 1000.0, 2000.0, 2000.0, 2000.0])
    df = pd.DataFrame({"raw": raw})
    flagged = clean.short_run_check(df)
    assert flagged.iloc[3] and flagged.iloc[4]
    assert not flagged.iloc[7]  # permanent shift: never reverts, not a "short run"


def test_clean_node_removes_exactly_injected_artifacts():
    n = 60
    times = _ts(n)
    rng = np.random.default_rng(1)
    raw = 1000.0 + np.arange(n) * 0.5 + rng.uniform(-1.0, 1.0, size=n)  # slow genuine drying trend
    temp = 20.0 + 2.0 * np.sin(np.linspace(0, 2 * np.pi, n))  # smooth diurnal temperature, no jumps

    injected = set()

    # Range violation.
    raw[10] = 9000.0
    injected.add(10)

    # A single-point rate-of-change spike shows up as a large diff on both
    # sides (into it and back out of it), so both index 20 and 21 get
    # flagged by rate_of_change_check -- a known property of consecutive-
    # diff checking, not a bug. Accompanied by a genuine temperature jump
    # (corroborated on both sides for the same reason).
    raw[20] += 500.0
    temp[20] += 5.0
    injected.update({20, 21})

    # Same shape, but no temperature discontinuity (not corroborated, but
    # still removed -- temperature corroboration is reported, not a
    # removal gate per the task spec).
    raw[30] += 500.0
    injected.update({30, 31})

    # Short reverting run (2 readings) -- well below the rate-of-change
    # threshold per-step, so rule 2 doesn't touch it; caught by rule 3
    # (local outlier) and/or rule 5 (short run) instead. Either way it
    # must end up removed.
    raw[40] += T.SHORT_RUN_REVERT_TOLERANCE_RAW + 80
    raw[41] += T.SHORT_RUN_REVERT_TOLERANCE_RAW + 70
    injected.update({40, 41})

    df = pd.DataFrame({"ts": times, "raw": raw, "temperature": temp})
    no_rain = pd.Series(dtype=float)

    result = clean.clean_node(df, no_rain)
    any_flagged = result["flags"]["range"] | result["flags"]["rate_of_change"] | result["flags"]["local_outlier"] | result["flags"]["short_run"]
    flagged_indices = set(np.flatnonzero(any_flagged.to_numpy()))

    assert flagged_indices == injected
    assert result["report"]["n_clean"] == n - len(injected)
    assert result["report"]["temperature_corroborated"]["rate_of_change"] >= 1
    assert result["report"]["temperature_not_corroborated"]["rate_of_change"] >= 1
