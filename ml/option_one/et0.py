"""Reference evapotranspiration (ET0).

Primary source is Open-Meteo's `et0_fao_evapotranspiration` (data_weather.py) --
training and forecast pull from the same API, which the spec calls out as
mattering more than it sounds. Hargreaves-Samani lives here as an offline
fallback / sanity check when only min/max temperature is available, and needs
no measured radiation -- Ra is pure geometry from latitude and day-of-year.
"""

from __future__ import annotations

import numpy as np


def extraterrestrial_radiation_mm_day(lat_deg: float, day_of_year: np.ndarray) -> np.ndarray:
    """Ra in mm/day equivalent (FAO-56 eq. 21), vectorized over day-of-year."""
    lat = np.radians(lat_deg)
    doy = np.asarray(day_of_year, dtype=float)

    dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * doy)  # inverse relative earth-sun distance
    decl = 0.409 * np.sin(2 * np.pi / 365 * doy - 1.39)  # solar declination

    x = -np.tan(lat) * np.tan(decl)
    x = np.clip(x, -1.0, 1.0)
    sunset_angle = np.arccos(x)

    Gsc = 0.0820  # solar constant, MJ m-2 min-1
    Ra_MJ = (
        (24 * 60 / np.pi)
        * Gsc
        * dr
        * (
            sunset_angle * np.sin(lat) * np.sin(decl)
            + np.cos(lat) * np.cos(decl) * np.sin(sunset_angle)
        )
    )
    return Ra_MJ * 0.408  # MJ m-2 day-1 -> mm/day (FAO-56 eq. 20)


def hargreaves_samani(
    t_max: np.ndarray, t_min: np.ndarray, lat_deg: float, day_of_year: np.ndarray
) -> np.ndarray:
    """ET0 in mm/day from daily max/min temperature only (Hargreaves-Samani 1985)."""
    t_max = np.asarray(t_max, dtype=float)
    t_min = np.asarray(t_min, dtype=float)
    t_mean = (t_max + t_min) / 2
    t_range = np.clip(t_max - t_min, 0, None)
    Ra = extraterrestrial_radiation_mm_day(lat_deg, day_of_year)
    return 0.0023 * (t_mean + 17.8) * np.sqrt(t_range) * Ra
