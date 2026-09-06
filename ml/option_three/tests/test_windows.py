"""Synthetic leakage test for events/windows.py: a hand-designed raw series
with known rain events (one big event with a real sensor response, one
small event the sensor does NOT react to, and a second big event with a
real response) and known window boundaries, verifying find_rain_events,
detect_sign_convention, and find_windows all agree with hand-computed
expectations -- not just that the functions run.

Series design (all times UTC, sign convention = wetter-is-lower-raw, the
capacitive-typical case):

  h=0..4h    : raw falls 700 -> 500 (still wetting, right after rain A)
  h=4..240h  : raw rises 500 -> 972 at +2/hour (drying; small rain at
               h=108h happens here but the sensor doesn't react to it)
  h=240..246h: raw falls 972 -> 402 at -95/hour (rain B's response dip)
  h=246..576h: raw rises 402 -> 1062 at +2/hour (drying to end of record)

Rates are chosen to divide evenly at the segment boundaries (all of which
land exactly on the 20-minute reading grid) so expected values are exact
in floating point, not just approximately equal.

Rain events: A = hours 0,1,2 of day 1 (6mm/hour); small = hour 108 (1mm);
B = hours 240,241,242 (6mm/hour). Record ends at h=576 (day 25).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.option_three.events import windows as W
from ml.option_three.configs import window_thresholds as T

START = pd.Timestamp("2026-01-01T00:00", tz="UTC")


def _raw_at_hours(h: np.ndarray) -> np.ndarray:
    raw = np.empty_like(h, dtype=float)
    seg1 = h <= 4
    seg2 = (h > 4) & (h <= 240)
    seg3 = (h > 240) & (h <= 246)
    seg4 = h > 246
    raw[seg1] = 700.0 - 50.0 * h[seg1]
    raw[seg2] = 500.0 + 2.0 * (h[seg2] - 4.0)
    raw[seg3] = 972.0 - 95.0 * (h[seg3] - 240.0)
    raw[seg4] = 402.0 + 2.0 * (h[seg4] - 246.0)
    return raw


def _build_readings():
    times = pd.date_range(START, START + pd.Timedelta(hours=576), freq="20min", tz="UTC")
    hours = (times - START).total_seconds() / 3600.0
    raw = _raw_at_hours(hours.to_numpy())
    return pd.DataFrame({"ts": times, "raw": raw})


def _build_hourly_precip():
    wet_times = [
        START + pd.Timedelta(hours=0),
        START + pd.Timedelta(hours=1),
        START + pd.Timedelta(hours=2),
        START + pd.Timedelta(hours=108),  # small, unresponsive rain
        START + pd.Timedelta(hours=240),
        START + pd.Timedelta(hours=241),
        START + pd.Timedelta(hours=242),
    ]
    values = [6.0, 6.0, 6.0, 1.0, 6.0, 6.0, 6.0]
    return pd.Series(values, index=pd.DatetimeIndex(wet_times)).sort_index()


def test_find_rain_events_merges_contiguous_hours_and_splits_isolated_ones():
    events = W.find_rain_events(_build_hourly_precip())
    assert len(events) == 3
    a, small, b = events
    assert a.start == START and a.end == START + pd.Timedelta(hours=2)
    assert a.total_mm == 18.0
    assert small.start == small.end == START + pd.Timedelta(hours=108)
    assert small.total_mm == 1.0
    assert b.start == START + pd.Timedelta(hours=240) and b.end == START + pd.Timedelta(hours=242)
    assert b.total_mm == 18.0


def test_detect_sign_convention_identifies_capacitive_style():
    readings = _build_readings()
    events = W.find_rain_events(_build_hourly_precip())
    sign = W.detect_sign_convention(readings, events)
    assert sign == -1


def test_find_windows_matches_hand_computed_boundaries():
    readings = _build_readings()
    events = W.find_rain_events(_build_hourly_precip())
    kept, all_windows, no_response = W.find_windows(node_id=1, readings=readings, rain_events=events, sign=-1)

    assert len(kept) == 2
    assert kept == all_windows  # neither window is short enough to be discarded here

    w1, w2 = kept
    assert w1.start == START + pd.Timedelta(hours=4)
    assert w1.end == START + pd.Timedelta(hours=240)
    assert w1.start_value == 500.0
    assert w1.end_value == 972.0
    assert w1.termination_reason == "rain"
    assert w1.duration_days > T.MIN_WINDOW_DAYS

    assert w2.start == START + pd.Timedelta(hours=246)
    assert w2.end == START + pd.Timedelta(hours=576)
    assert w2.start_value == 402.0
    assert w2.end_value == 1062.0
    assert w2.termination_reason == "end_of_record"
    assert w2.duration_days > T.MIN_WINDOW_DAYS

    assert len(no_response) == 1
    assert no_response[0]["rain_start"] == START + pd.Timedelta(hours=108)


def test_min_window_days_filters_short_windows():
    short = W.Window(1, START, START + pd.Timedelta(days=2), 500.0, 600.0, "rain")
    long = W.Window(1, START, START + pd.Timedelta(days=10), 500.0, 700.0, "end_of_record")
    kept = [w for w in [short, long] if w.duration_days >= T.MIN_WINDOW_DAYS]
    assert kept == [long]
