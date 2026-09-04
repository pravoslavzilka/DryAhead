"""Lag/rolling feature-table construction, one row per node-day.

Every feature here must be computable at prediction time from a weather
forecast plus past sensor readings -- see build_feature_table's docstring
for the leakage rule this module is built around, and tests/test_features.py
for the regression test that exercises it directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import RAIN_THRESHOLD_MM, ROLLING_WINDOWS

WEATHER_COLS = [
    "precipitation_sum", "et0_fao_evapotranspiration", "temperature_2m_max",
    "temperature_2m_min", "relative_humidity_2m_mean", "wind_speed_10m_max",
    "shortwave_radiation_sum",
]


def _vpd_kpa(temp_mean_c: pd.Series, rh_mean_pct: pd.Series) -> pd.Series:
    """Vapor pressure deficit, kPa, from mean daily temp + mean RH (Tetens
    saturation-vapor-pressure formula)."""
    es = 0.6108 * np.exp(17.27 * temp_mean_c / (temp_mean_c + 237.3))
    return es * (1 - rh_mean_pct / 100.0)


def _days_since_rain(rain: pd.Series, threshold_mm: float) -> pd.Series:
    """Integer days since the last day with rain > threshold_mm, as of and
    including the current day (0 if today itself is a rain day). Uses only
    rain observed on or before the current day -- no look-ahead."""
    is_rain = rain > threshold_mm
    # cumulative count of rain-days up to and including today, as a group key:
    # every day since the last rain-day shares the same group id.
    group = is_rain.cumsum()
    days_since = is_rain.groupby(group).cumcount()
    # rows before the first-ever rain day have no "last rain day" -- leave NaN
    days_since = days_since.astype("float64")
    days_since[group == 0] = np.nan
    return days_since


def build_node_table(node_id: int, moisture: pd.DataFrame, weather: pd.DataFrame,
                      elevation: float | None, horizons: list[int]) -> pd.DataFrame:
    """One node's full daily table: continuous calendar-day index spanning
    the node's moisture record, weather features (using only weather up to
    and including the row's own date), lag/rolling features, and
    target_h = raw_mean[t+h] - raw_mean[t] for each horizon in `horizons`.

    Leakage rule: every column except the target_h_* columns must be
    computable from data with date <= t. Weather is joined by date and
    used at its own date or earlier (rolling windows), never from t+1
    onward for a feature. Targets are the one deliberate exception -- they
    read t+h and exist only as training labels, never as model inputs.
    """
    start, end = moisture.index.min(), moisture.index.max()
    idx = pd.date_range(start, end, freq="D")

    # `weather` is expected to span from well before `start` (the caller
    # fetches max(ROLLING_WINDOWS) extra days of pre-history) through `end`.
    # Rolling windows are computed on that FULL span first, so a row at
    # `start` can still see a real 90-day-back sum from before the node's
    # own moisture record began -- only *then* is everything reindexed down
    # to `idx`. Truncating to `idx` before rolling would silently blank out
    # every long window for the node's early rows, which given each node's
    # short deployment record (order of 60-90 days total) would have been
    # most of the dataset, not just a warm-up edge case.
    w = weather.sort_index().copy()

    for lag in (1, 2, 3):
        w[f"lag_precip_t{lag}"] = w["precipitation_sum"].shift(lag)

    for win in ROLLING_WINDOWS:
        rain_sum = w["precipitation_sum"].rolling(win, min_periods=win).sum()
        et0_sum = w["et0_fao_evapotranspiration"].rolling(win, min_periods=win).sum()
        w[f"rain_sum_{win}d"] = rain_sum
        w[f"et0_sum_{win}d"] = et0_sum
        w[f"water_balance_{win}d"] = rain_sum - et0_sum

    w["days_since_rain"] = _days_since_rain(w["precipitation_sum"], RAIN_THRESHOLD_MM)

    temp_mean = (w["temperature_2m_max"] + w["temperature_2m_min"]) / 2.0
    vpd = _vpd_kpa(temp_mean, w["relative_humidity_2m_mean"])
    for win in (7, 30):
        w[f"temp_mean_{win}d"] = temp_mean.rolling(win, min_periods=win).mean()
        w[f"temp_max_{win}d"] = w["temperature_2m_max"].rolling(win, min_periods=win).max()
        w[f"vpd_mean_{win}d"] = vpd.rolling(win, min_periods=win).mean()
        w[f"vpd_max_{win}d"] = vpd.rolling(win, min_periods=win).max()

    doy = w.index.dayofyear.values.astype("float64")
    w["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    w["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)

    # Now bring in the node's own moisture series (only ever spans `idx`,
    # no pre-history exists for it -- there was no deployment before
    # `start`) and reindex the whole thing down to the node's real span.
    m = moisture.reindex(idx)
    df = w.reindex(idx).copy()
    df.insert(0, "node_id", node_id)
    df["theta_raw"] = m["raw_mean"]
    df["n_readings"] = m["n_readings"]
    for lag in (1, 2, 3, 7, 14):
        df[f"lag_moisture_t{lag}"] = df["theta_raw"].shift(lag)

    df["elevation_m"] = elevation

    for h in horizons:
        df[f"target_h{h}"] = df["theta_raw"].shift(-h) - df["theta_raw"]

    return df


def build_feature_table(moisture_by_node: dict[int, pd.DataFrame], weather_by_node: dict[int, pd.DataFrame],
                         elevation_by_node: dict[int, float | None], horizons: list[int]) -> pd.DataFrame:
    """Concatenate build_node_table across all nodes into one long table."""
    tables = [
        build_node_table(node_id, moisture_by_node[node_id], weather_by_node[node_id],
                          elevation_by_node.get(node_id), horizons)
        for node_id in sorted(moisture_by_node)
    ]
    out = pd.concat(tables, axis=0)
    out.index.name = "date"
    return out.reset_index()


FEATURE_COLUMNS = (
    WEATHER_COLS
    + [f"lag_moisture_t{lag}" for lag in (1, 2, 3, 7, 14)]
    + [f"lag_precip_t{lag}" for lag in (1, 2, 3)]
    + [f"rain_sum_{w}d" for w in ROLLING_WINDOWS]
    + [f"et0_sum_{w}d" for w in ROLLING_WINDOWS]
    + [f"water_balance_{w}d" for w in ROLLING_WINDOWS]
    + ["days_since_rain"]
    + [f"temp_mean_{w}d" for w in (7, 30)]
    + [f"temp_max_{w}d" for w in (7, 30)]
    + [f"vpd_mean_{w}d" for w in (7, 30)]
    + [f"vpd_max_{w}d" for w in (7, 30)]
    + ["doy_sin", "doy_cos", "node_id", "elevation_m"]
)
