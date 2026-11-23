"""Daily evaporative demand from the Zajezova station, split into the two
halves of FAO-56 Penman-Monteith so the drying model can weight them
separately (drydown.py's `a` and `b`):

                      0.408 * delta * Rn
    rad_mm  = ---------------------------------      sun: energy to evaporate water
               delta + gamma * (1 + 0.34 * u2)

               gamma * (900 / (T + 273)) * u2 * (es - ea)
    aero_mm = ------------------------------------------   air: dryness x wind
               delta + gamma * (1 + 0.34 * u2)

rad_mm + aero_mm is ordinary FAO-56 reference ET0 (mm/day). Computed from the
station's own minute data (meteotekov.py), per station-local day.

Over 2026-06-29..09-24 this came out ~28% below Open-Meteo's ET0 (station
wind averages only 0.6-2 m/s -- a sheltered site or an anemometer below the
standard 2 m), but tracks it day to day at r=0.95. The scale doesn't matter
for the drying model: its fitted `a`/`b` absorb any constant factor.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from config import LAT, STATION_ELEVATION_M
from et0 import extraterrestrial_radiation_mm_day
from meteotekov import DEFAULT_DB

MIN_ROWS_PER_DAY = 720  # at least half a day of complete minute rows
ALBEDO = 0.23  # FAO-56 reference grass
STEFAN_BOLTZMANN = 4.903e-9  # MJ K-4 m-2 day-1


def _sat_vp(t_c):
    """Saturation vapour pressure, kPa (FAO-56 eq. 11)."""
    return 0.6108 * np.exp(17.27 * t_c / (t_c + 237.3))


def daily_pm_terms(db_path: str = DEFAULT_DB) -> pd.DataFrame:
    """Per local day: rad_mm, aero_mm, et0_mm, plus the drivers behind them
    (t_mean, vpd_kpa, wind_ms, rs_mj). Days with too few complete rows are
    left out; callers decide how to fill them."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql(
        "SELECT date, temperature_c AS t, humidity_pct AS rh, pressure_hpa AS p, "
        "wind_speed_kmh AS wind, solar_wm2 AS rs FROM observations",
        conn,
    )
    conn.close()
    df = df.dropna()
    df["ea"] = _sat_vp(df["t"]) * df["rh"] / 100  # actual vapour pressure, per minute

    g = df.groupby("date")
    d = pd.DataFrame({
        "n": g.size(),
        "t_mean": g["t"].mean(),
        "t_max": g["t"].max(),
        "t_min": g["t"].min(),
        "ea": g["ea"].mean(),
        "p_kpa": g["p"].mean() / 10,
        "wind_ms": g["wind"].mean() / 3.6,  # assumes the anemometer is at ~2 m
        "rs_mj": g["rs"].mean() * 0.0864,  # mean W/m2 -> MJ/m2/day
    })
    d = d[d["n"] >= MIN_ROWS_PER_DAY]
    d.index = pd.to_datetime(d.index)

    es = (_sat_vp(d["t_max"]) + _sat_vp(d["t_min"])) / 2
    ra = extraterrestrial_radiation_mm_day(LAT, d.index.dayofyear.to_numpy()) / 0.408  # MJ/m2/day
    rso = (0.75 + 2e-5 * STATION_ELEVATION_M) * ra  # clear-sky radiation
    rnl = (
        STEFAN_BOLTZMANN
        * ((d["t_max"] + 273.16) ** 4 + (d["t_min"] + 273.16) ** 4) / 2
        * (0.34 - 0.14 * np.sqrt(d["ea"]))
        * (1.35 * np.minimum(d["rs_mj"] / rso, 1.0) - 0.35)
    )
    rn = (1 - ALBEDO) * d["rs_mj"] - rnl

    delta = 4098 * _sat_vp(d["t_mean"]) / (d["t_mean"] + 237.3) ** 2
    gamma = 0.000665 * d["p_kpa"]
    denom = delta + gamma * (1 + 0.34 * d["wind_ms"])

    out = pd.DataFrame({
        "rad_mm": 0.408 * delta * rn / denom,
        "aero_mm": gamma * (900 / (d["t_mean"] + 273)) * d["wind_ms"] * (es - d["ea"]) / denom,
        "t_mean": d["t_mean"],
        "vpd_kpa": es - d["ea"],
        "wind_ms": d["wind_ms"],
        "rs_mj": d["rs_mj"],
    })
    out.insert(2, "et0_mm", out["rad_mm"] + out["aero_mm"])
    return out
