"""Step 3 -- sub-daily ET0.

Primary method: Open-Meteo's hourly `et0_fao_evapotranspiration` variable,
which Open-Meteo computes via Penman-Monteith from its own hourly weather
fields (https://open-meteo.com/en/docs) -- requesting it directly *is* the
Penman-Monteith path the task spec calls out, with no need to reimplement
the equation here.

Fallback method (only used if that column is missing/all-NaN for the
requested range): disaggregate Open-Meteo's daily ET0 across daylight
hours with a solar-geometry shape (sine of solar elevation, zero at
night, peaked at solar noon) -- a flat 24-hour spread would dry the soil
overnight in the model, which is wrong.

`hourly_et0()` reports which method was actually used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..configs import site


def solar_elevation_weight(times: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    """Unitless daylight weight in [0, 1] per hour, proportional to
    sin(solar elevation) -- 0 at night, peaked at solar noon. Standard
    solar-geometry approximation (Cooper's declination formula + a
    simplified equation-of-time term), no external dependency."""
    doy = times.dayofyear.to_numpy()
    hour_utc = times.hour.to_numpy() + times.minute.to_numpy() / 60.0

    decl = np.radians(23.45) * np.sin(2 * np.pi * (284 + doy) / 365.0)
    lat_r = np.radians(lat)

    b = 2 * np.pi * (doy - 81) / 364.0
    eot_minutes = 9.87 * np.sin(2 * b) - 7.53 * np.cos(b) - 1.5 * np.sin(b)
    solar_noon_utc = 12.0 - lon / 15.0 - eot_minutes / 60.0

    hour_angle = np.radians(15.0 * (hour_utc - solar_noon_utc))
    sin_elev = np.sin(lat_r) * np.sin(decl) + np.cos(lat_r) * np.cos(decl) * np.cos(hour_angle)
    return np.clip(sin_elev, 0.0, None)


def disaggregate_daily_et0(daily_et0: pd.Series, lat: float = site.LAT, lon: float = site.LON) -> pd.Series:
    """daily_et0: mm/day indexed by day (UTC midnight). Returns mm/hour
    indexed by hour-start, summing back to each day's total."""
    parts = []
    for day, total_mm in daily_et0.items():
        day_hours = pd.date_range(day, periods=24, freq="h", tz="UTC")
        weights = solar_elevation_weight(day_hours, lat, lon)
        wsum = weights.sum()
        hourly_mm = np.zeros(len(day_hours)) if wsum <= 0 else total_mm * weights / wsum
        parts.append(pd.Series(hourly_mm, index=day_hours))
    return pd.concat(parts).sort_index()


def hourly_et0(weather: dict, lat: float = site.LAT, lon: float = site.LON) -> tuple[pd.Series, str]:
    """weather: the dict returned by data.loaders.fetch_hourly_weather.
    Returns (hourly_et0_mm_series, method_label)."""
    hourly = weather["hourly"]
    if weather["et0_method"] == "open-meteo-hourly-penman-monteith":
        s = pd.Series(hourly["et0_fao_evapotranspiration"].to_numpy(dtype=float), index=pd.DatetimeIndex(hourly["time"]))
        return s, weather["et0_method"]

    daily = weather.get("daily")
    if daily is None or "et0_fao_evapotranspiration" not in daily.columns:
        raise ValueError("no hourly or daily et0_fao_evapotranspiration available from Open-Meteo response")
    daily_series = pd.Series(daily["et0_fao_evapotranspiration"].to_numpy(dtype=float), index=pd.DatetimeIndex(daily["time"]))
    return disaggregate_daily_et0(daily_series, lat, lon), weather["et0_method"]
