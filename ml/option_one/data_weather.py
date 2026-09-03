"""Weather inputs from Open-Meteo: historical daily for calibration, ensemble
forecast for prediction. Both come from the same API/variable
(`et0_fao_evapotranspiration`) deliberately -- training and inference should
see ET0 computed the same way, per the spec.
"""

from __future__ import annotations

import re

import pandas as pd
import requests

from config import LAT, LON

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"

DAILY_VARS = "precipitation_sum,et0_fao_evapotranspiration"


def fetch_historical_daily(start_date: str, end_date: str, timeout: float = 30.0) -> pd.DataFrame:
    """Daily precipitation_sum (mm) and et0_fao_evapotranspiration (mm) for
    [start_date, end_date] (YYYY-MM-DD), indexed by date."""
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start_date,
        "end_date": end_date,
        "daily": DAILY_VARS,
        "timezone": "UTC",
    }
    resp = requests.get(ARCHIVE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    daily = resp.json()["daily"]
    df = pd.DataFrame(
        {
            "rain_mm": daily["precipitation_sum"],
            "et0_mm": daily["et0_fao_evapotranspiration"],
        },
        index=pd.to_datetime(daily["time"]),
    )
    return df


def fetch_forecast_ensemble(days: int = 35, model: str = "icon_seamless", timeout: float = 30.0) -> dict[str, pd.DataFrame]:
    """Ensemble forecast members for the next `days` days.

    Returns {"rain_mm": DataFrame[date x member], "et0_mm": DataFrame[date x member]}
    -- one trajectory per ensemble member (ICON's ensemble has 40 members by
    default; pass model="ecmwf_ifs025" for ECMWF's 50-member ensemble where
    available on your plan).
    """
    params = {
        "latitude": LAT,
        "longitude": LON,
        "daily": DAILY_VARS,
        "forecast_days": days,
        "models": model,
        "timezone": "UTC",
    }
    resp = requests.get(ENSEMBLE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    daily = resp.json()["daily"]
    dates = pd.to_datetime(daily["time"])

    member_re = re.compile(r"^(rain|precipitation_sum|et0_fao_evapotranspiration)(?:_member(\d+))?$")
    rain_cols: dict[str, list] = {}
    et0_cols: dict[str, list] = {}
    for key, values in daily.items():
        m = member_re.match(key)
        if not m:
            continue
        var, member = m.groups()
        member = member or "00"
        if var == "precipitation_sum":
            rain_cols[member] = values
        elif var == "et0_fao_evapotranspiration":
            et0_cols[member] = values

    rain_df = pd.DataFrame(rain_cols, index=dates).sort_index(axis=1)
    et0_df = pd.DataFrame(et0_cols, index=dates).sort_index(axis=1)
    return {"rain_mm": rain_df, "et0_mm": et0_df}
