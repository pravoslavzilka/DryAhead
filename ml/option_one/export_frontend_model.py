"""Export the fitted drying + wetting models for the dashboard's drought
forecast (frontend/src/lib/droughtForecast.js runs them in the browser).

Reads run_drydown.py / run_wetting.py outputs and writes
frontend/src/data/droughtModel.json. Re-run after refitting, then commit that
file -- the deployed dashboard reads it at build time.

The dashboard only has Open-Meteo's forecast, but the models were fitted on
the Zajezova station's ET0, which runs well below Open-Meteo's (sheltered
anemometer). `et0_scale` = station ET0 / Open-Meteo ET0 over the fitting
period, so the browser can put forecast ET0 on the station's scale.

Run: `python export_frontend_model.py` (needs outputs/ from both runners).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import requests

import station_weather
from config import DRYDOWN_START, LAT, LON, LOCAL_TZ, MODEL_NODE_IDS

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUTS = os.path.join(HERE, "outputs")
TARGET = os.path.join(HERE, "..", "..", "frontend", "src", "data", "droughtModel.json")

DRYING_VARIANT = "single_rate"  # validated equal/better than split_ab on every node (README)


def et0_scale(start: str, end: str) -> tuple[float, float]:
    """Station ET0 / Open-Meteo archive ET0 (ratio of sums) and their daily r."""
    station = station_weather.daily_pm_terms()["et0_mm"][start:end]
    resp = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude": LAT, "longitude": LON, "start_date": start, "end_date": end,
        "daily": "et0_fao_evapotranspiration", "timezone": LOCAL_TZ,
    }, timeout=30)
    resp.raise_for_status()
    d = resp.json()["daily"]
    om = pd.Series(d["et0_fao_evapotranspiration"], index=pd.to_datetime(d["time"]), dtype=float)
    both = pd.concat([station, om], axis=1, keys=["station", "om"]).dropna()
    return float(both.station.sum() / both.om.sum()), float(np.corrcoef(both.station, both.om)[0, 1])


def main() -> int:
    with open(os.path.join(OUTPUTS, "drydown_params.json")) as f:
        drying = json.load(f)
    with open(os.path.join(OUTPUTS, "wetting_params.json")) as f:
        wet_params = json.load(f)
    with open(os.path.join(OUTPUTS, "wetting_validation.json")) as f:
        wet_val = json.load(f)
    with open(os.path.join(OUTPUTS, "drydown_validation.json")) as f:
        dry_val = json.load(f)

    end = (pd.Timestamp.now(tz=LOCAL_TZ) - pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    scale, r = et0_scale(DRYDOWN_START, end)
    print(f"et0_scale {scale:.3f} (station / Open-Meteo, daily r={r:.2f}, {DRYDOWN_START}..{end})")

    nodes = {}
    for node_id in MODEL_NODE_IDS:
        key = str(node_id)
        dp = drying[key][DRYING_VARIANT]
        best = wet_params[key]["best_loo"]
        wet = {"model": best, **wet_params[key][best], "floor": wet_val[key]["floor_counts"]}
        # plant stress starts where Ks begins to drop: depletion past p * TAW
        stress_raw = dp["raw_fc"] + dp["p"] * (dp["raw_wp"] - dp["raw_fc"])
        rmse7 = dry_val[key][DRYING_VARIANT]["rmse_by_horizon"]["validation"].get("7", {}).get("model", {}).get("rmse")
        nodes[key] = {
            "drying": {k: dp[k] for k in ("raw_fc", "raw_wp", "p", "tau_d", "a")},
            "stress_raw": stress_raw,
            "wetting": wet,
            "validation_rmse_7d_counts": rmse7,
        }
        print(f"node {node_id}: stress at raw {stress_raw:.0f}, wetting model '{best}'")

    out = {
        "generated": date.today().isoformat(),
        "fitted_on": f"{DRYDOWN_START}..{end}",
        "timezone": LOCAL_TZ,
        "et0_scale": scale,
        "et0_scale_r": r,
        "drying_variant": DRYING_VARIANT,
        "nodes": nodes,
    }
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    with open(TARGET, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {os.path.normpath(TARGET)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
