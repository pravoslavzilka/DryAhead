"""Unit tests for model/drydown.py: the Ks kink, uneven-timestep ET0
integration, and a hand-checkable unstressed simulation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.option_three.model.drydown import integrate_et0, ks, precompute_et0_intervals, simulate_window


def test_ks_full_availability_below_threshold():
    # depletion well below p*span -> Ks = 1
    assert ks(depletion=10.0, span=100.0, p=0.5) == 1.0
    assert ks(depletion=50.0, span=100.0, p=0.5) == 1.0  # exactly at threshold


def test_ks_declines_linearly_above_threshold():
    # span=100, p=0.5 -> threshold=50. At depletion=75 (halfway between
    # threshold and span), Ks should be exactly 0.5.
    assert ks(depletion=75.0, span=100.0, p=0.5) == pytest.approx(0.5)


def test_ks_zero_at_and_beyond_span():
    assert ks(depletion=100.0, span=100.0, p=0.5) == pytest.approx(0.0)
    assert ks(depletion=150.0, span=100.0, p=0.5) == 0.0


def test_integrate_et0_partial_hours():
    hours = pd.date_range("2026-01-01T00:00", periods=3, freq="h", tz="UTC")
    series = pd.Series([1.0, 2.0, 3.0], index=hours)  # mm/hour in each bucket

    # Fully within the first bucket: half of hour 0's 1.0 mm/hour.
    start = pd.Timestamp("2026-01-01T00:00", tz="UTC")
    end = pd.Timestamp("2026-01-01T00:30", tz="UTC")
    assert integrate_et0(series, start, end) == pytest.approx(0.5)

    # Spans hour 0 (last 30 min) and hour 1 (first 30 min):
    # 0.5*1.0 + 0.5*2.0 = 1.5
    start = pd.Timestamp("2026-01-01T00:30", tz="UTC")
    end = pd.Timestamp("2026-01-01T01:30", tz="UTC")
    assert integrate_et0(series, start, end) == pytest.approx(1.5)

    # Zero-length interval.
    t = pd.Timestamp("2026-01-01T01:00", tz="UTC")
    assert integrate_et0(series, t, t) == 0.0


def test_simulate_window_matches_manual_calc_when_unstressed():
    # Constant ET0 = 1.0 mm/hour, Kc=1, scale=10 raw/mm -> loss = 10 raw/hour
    # while Ks=1 (depletion stays far below p*span throughout this short
    # run, so the kink never engages -- pure linear loss, hand-checkable).
    times = pd.date_range("2026-01-01T00:00", periods=4, freq="h", tz="UTC")
    hourly_et0 = pd.Series([1.0, 1.0, 1.0, 1.0], index=times)

    wet_ref = 500.0
    dry_ref = 4000.0  # span=3500, p=0.5 -> threshold depletion=1750, never reached below
    sim = simulate_window(
        times, start_value=500.0, wet_ref=wet_ref, dry_ref=dry_ref, kc=1.0, p=0.5,
        scale_mm_to_raw=10.0, et0_intervals=precompute_et0_intervals(times, hourly_et0),
    )
    expected = np.array([500.0, 510.0, 520.0, 530.0])
    np.testing.assert_allclose(sim, expected)


def test_simulate_window_direction_follows_dry_ref_vs_wet_ref():
    # dry_ref < wet_ref -> drying decreases raw (the other sign convention).
    times = pd.date_range("2026-01-01T00:00", periods=2, freq="h", tz="UTC")
    hourly_et0 = pd.Series([1.0], index=times[:1])
    sim = simulate_window(
        times, start_value=1000.0, wet_ref=1000.0, dry_ref=100.0, kc=1.0, p=0.5,
        scale_mm_to_raw=10.0, et0_intervals=precompute_et0_intervals(times, hourly_et0),
    )
    assert sim[1] < sim[0]
    assert sim[1] == pytest.approx(990.0)
