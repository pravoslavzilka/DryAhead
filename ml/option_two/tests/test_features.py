"""Regression tests for data/features.py, especially the leakage rule:
every feature column must be computable from data with date <= t. Uses a
synthetic series (no network) where leakage would be obvious if present --
a `theta_raw` series that jumps to a distinctive, easy-to-spot value on a
single future day, and a check that no feature at day t reflects it.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.features import FEATURE_COLUMNS, _days_since_rain, build_node_table
from config import ROLLING_WINDOWS


def _synthetic_series(n_days: int = 120, seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")

    rain = rng.exponential(1.5, size=n_days)
    rain[rng.random(n_days) < 0.6] = 0.0  # mostly dry days
    et0 = rng.uniform(2, 6, size=n_days)
    tmax = rng.uniform(15, 30, size=n_days)
    tmin = tmax - rng.uniform(5, 12, size=n_days)
    rh = rng.uniform(30, 90, size=n_days)
    wind = rng.uniform(2, 15, size=n_days)
    rad = rng.uniform(5, 30, size=n_days)

    weather = pd.DataFrame({
        "precipitation_sum": rain, "et0_fao_evapotranspiration": et0,
        "temperature_2m_max": tmax, "temperature_2m_min": tmin,
        "relative_humidity_2m_mean": rh, "wind_speed_10m_max": wind,
        "shortwave_radiation_sum": rad,
    }, index=dates)

    # theta: a smooth-ish random walk driven by rain-minus-et0, so it isn't
    # pure noise but also isn't a fixed formula the model could special-case.
    theta = 2000 + np.cumsum((rain * 30 - et0 * 5) + rng.normal(0, 5, size=n_days))
    moisture = pd.DataFrame({
        "raw_mean": theta, "raw_min": theta - 10, "raw_max": theta + 10,
        "n_readings": np.full(n_days, 60),
    }, index=dates)

    return moisture, weather


def test_no_feature_uses_future_moisture():
    """Plant a single, distinctive future spike in theta_raw (day 100 jumps
    by +100000, far outside the walk's normal range) and assert that no
    feature computed for any day t < 100 reflects it -- i.e. every feature
    at day t-1 (the last row entirely unaffected by the spike) is bit-for-bit
    identical whether or not the spike is present downstream."""
    moisture, weather = _synthetic_series(n_days=120)

    moisture_clean = moisture.copy()
    moisture_spiked = moisture.copy()
    spike_day = moisture.index[100]
    moisture_spiked.loc[spike_day, "raw_mean"] += 100_000.0

    table_clean = build_node_table(1, moisture_clean, weather, elevation=600.0, horizons=[1, 7, 14, 28])
    table_spiked = build_node_table(1, moisture_spiked, weather, elevation=600.0, horizons=[1, 7, 14, 28])

    before_spike = table_clean.index < spike_day
    feature_cols = [c for c in FEATURE_COLUMNS if c != "node_id"]

    a = table_clean.loc[before_spike, feature_cols]
    b = table_spiked.loc[before_spike, feature_cols]
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9,
                                   obj="features at t < spike day, clean vs. spiked future")


def test_target_horizon_does_use_future_moisture():
    """Sanity-check the test above isn't vacuous: the *target* columns
    (which are meant to look ahead, by design) DO change when a future
    value the target's horizon window reaches is spiked -- confirms
    test_no_feature_uses_future_moisture would actually catch a real bug
    rather than passing because nothing in the table ever changes."""
    moisture, weather = _synthetic_series(n_days=120)
    moisture_spiked = moisture.copy()
    spike_day = moisture.index[100]
    moisture_spiked.loc[spike_day, "raw_mean"] += 100_000.0

    table_clean = build_node_table(1, moisture, weather, elevation=600.0, horizons=[1])
    table_spiked = build_node_table(1, moisture_spiked, weather, elevation=600.0, horizons=[1])

    # day 99 (index position 99): target_h1 = theta[100] - theta[99] --
    # this MUST differ once day 100 is spiked, or the target itself is
    # broken (which would also make the leakage test above meaningless).
    day99 = moisture.index[99]
    assert table_clean.loc[day99, "target_h1"] != pytest.approx(table_spiked.loc[day99, "target_h1"])


def test_lag_features_shift_correctly():
    moisture, weather = _synthetic_series(n_days=40)
    table = build_node_table(1, moisture, weather, elevation=600.0, horizons=[1])
    # lag_moisture_t1 at day t must equal theta_raw at day t-1, exactly.
    shifted = table["theta_raw"].shift(1)
    pd.testing.assert_series_equal(table["lag_moisture_t1"], shifted, check_names=False)


def test_rolling_windows_require_full_history():
    """A rolling sum with min_periods=window must be NaN until `window`
    full days of history exist -- a silent partial-window sum would
    understate uncertainty without anyone noticing. This fixture's weather
    and moisture both start on the same date (no pre-history buffer, unlike
    train.py's real fetch which asks for max(ROLLING_WINDOWS) extra days),
    so the transition from NaN to a real value should land exactly at
    row index `win - 1` (the first row with `win` full days behind it,
    itself included)."""
    moisture, weather = _synthetic_series(n_days=200)
    table = build_node_table(1, moisture, weather, elevation=600.0, horizons=[1])
    win = max(ROLLING_WINDOWS)
    col = f"rain_sum_{win}d"
    assert pd.isna(table[col].iloc[win - 2])
    assert not pd.isna(table[col].iloc[win - 1])
    # and the first valid value really is the sum of exactly the first `win` days
    expected = weather["precipitation_sum"].iloc[:win].sum()
    assert table[col].iloc[win - 1] == pytest.approx(expected)


def test_days_since_rain_no_lookahead():
    rain = pd.Series([0, 0, 3.0, 0, 0, 0, 5.0], index=pd.date_range("2026-01-01", periods=7))
    out = _days_since_rain(rain, threshold_mm=1.0)
    # day0,1: no rain yet ever -> NaN. day2: rain day -> 0. day3: 1 day since. day4: 2. day5: 3. day6: rain day -> 0.
    expected = pd.Series([np.nan, np.nan, 0, 1, 2, 3, 0], index=rain.index, dtype="float64")
    pd.testing.assert_series_equal(out, expected, check_names=False)


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
