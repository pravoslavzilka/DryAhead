"""Wetting model: how far a node's raw reading drops (gets wetter) when rain
falls. The counterpart of drydown.py, which covers everything between
wettings. Raw ADC counts per node, lower = wetter.

Per station rain event, the model predicts the drop in the node's reading:

    top layer store T (mm) -- the soil above the sensor. Hour by hour:
        T += rain;  overflow = max(T - s_top, 0);  T -= overflow
        T  = max(T - ET0_hour, 0)                  (dries between rains)
    drop = min(gain * overflow during the event,  x_before - floor)

  s_top  (mm)            how much rain the soil above the sensor holds back
  gain   (counts / mm)   how much the reading drops per mm that gets through
  floor  (counts)        the wettest reading this sensor gives -- node 4 sits
                         right at its `water` calibration after big storms

Why a store, not a fixed threshold: node 5 showed nothing for 10.8 mm on
08-20, then dropped ~680 counts on 12.8 mm the next evening -- the first rain
filled the layer above the sensor, the second came straight through. A
store that fills with rain and empties with evaporation carries that memory;
a fixed "first N mm don't count" rule can't.

Compared against simpler variants (run_wetting.py), each scored with
leave-one-event-out cross-validation because each node has only ~5 events
it responded to at all:
    none       -- predict no drop (the bar every model has to clear)
    linear     -- drop = gain * rain
    threshold  -- drop = gain * max(rain - s_top, 0)   (fixed, no memory)
    store      -- the top-layer store above
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from meteotekov import DEFAULT_DB

EVENT_GAP = pd.Timedelta("12h")  # rain separated by less than this is one event
MIN_EVENT_MM = 0.2  # the station's tipping-bucket resolution
RESPONSE_WINDOW = pd.Timedelta("48h")  # node 5 peaked 26 h after rain, node 1 38 h
SMALL_EVENT_MM = 1.0  # showers below this inside a bigger event's window are merged into it

MODELS = ("none", "linear", "threshold", "store")
BOUNDS = {"gain": (0.0, 300.0), "s_top": (0.0, 40.0)}
MODEL_PARAMS = {"none": (), "linear": ("gain",), "threshold": ("gain", "s_top"), "store": ("gain", "s_top")}


# --- Station inputs ------------------------------------------------------------

def station_rain_minutes(db_path: str = DEFAULT_DB) -> pd.Series:
    """Rain per minute (mm), UTC-indexed, from the station's running daily
    total (resets at local midnight). Missing cells are carried forward."""
    conn = sqlite3.connect(db_path)
    obs = pd.read_sql("SELECT date, ts_utc, precip_cum_mm FROM observations ORDER BY date, time", conn)
    conn.close()
    cum = obs.groupby("date")["precip_cum_mm"].ffill().fillna(0.0)
    inc = cum.groupby(obs["date"]).diff().fillna(cum).clip(lower=0.0)
    return pd.Series(inc.to_numpy(), index=pd.to_datetime(obs["ts_utc"], utc=True))


def hourly_et0(daily_et0: pd.Series, tz: str) -> pd.Series:
    """Daily station ET0 (local days, station_weather.daily_pm_terms) spread
    evenly over each day's hours, UTC-indexed."""
    idx = pd.date_range(daily_et0.index.min(), daily_et0.index.max() + pd.Timedelta(days=1),
                        freq="1h", inclusive="left", tz=tz)
    per_hour = daily_et0.reindex(idx.tz_localize(None).normalize()).to_numpy() / 24
    return pd.Series(per_hour, index=idx.tz_convert("UTC"))


def rain_events(rain_min: pd.Series) -> pd.DataFrame:
    """Group rainy minutes into events. Columns: start, end, mm, peak_mm_h."""
    wet = rain_min[rain_min > 0]
    gid = (wet.index.to_series().diff() > EVENT_GAP).cumsum().to_numpy()
    ev = pd.DataFrame({
        "start": wet.index.to_series().groupby(gid).min(),
        "end": wet.index.to_series().groupby(gid).max(),
        "mm": wet.groupby(gid).sum(),
    }).reset_index(drop=True)
    hourly = rain_min.resample("1h").sum()
    ev["peak_mm_h"] = [hourly[s.floor("h"):e.ceil("h")].max() for s, e in zip(ev.start, ev.end)]
    ev = ev[ev.mm >= MIN_EVENT_MM].reset_index(drop=True)
    return absorb_small_events(ev)


def absorb_small_events(ev: pd.DataFrame) -> pd.DataFrame:
    """A shower under SMALL_EVENT_MM that falls inside the previous event's
    response window is merged into it. Otherwise it cuts that window short
    and gets credited with the bigger rain's delayed response (node 1's
    38-hour response to 09-11's 22.6 mm landed on a 0.3 mm shower)."""
    rows = []
    for e in ev.to_dict("records"):
        if rows and e["mm"] < SMALL_EVENT_MM and e["start"] < rows[-1]["end"] + RESPONSE_WINDOW:
            prev = rows[-1]
            prev["mm"] += e["mm"]
            prev["end"] = max(prev["end"], e["end"])
            prev["peak_mm_h"] = max(prev["peak_mm_h"], e["peak_mm_h"])
        else:
            rows.append(dict(e))
    return pd.DataFrame(rows)


# --- Observed responses ----------------------------------------------------------

def measure_responses(hourly_raw: pd.Series, events: pd.DataFrame, threshold: float,
                      blocked: list[tuple[pd.Timestamp, pd.Timestamp]] = ()) -> pd.DataFrame:
    """Per event: the reading before the rain and how far its level dropped.

    Measured on a 24-hour rolling median, not raw hours: every node swings
    19-44 counts per day (wettest-looking in the evening), which otherwise
    shows up as small fake responses. `x_before` is the median of the 24 h
    before the rain; the level after is the lowest 24 h median within 48 h of
    the rain ending. That's the level the daily drying model carries on from.

    `blocked` are (onset, peak) spans of wettings with no station rain. A
    window stops early at the next event's start or a blocked onset, so
    those aren't credited to this rain; an event starting inside a blocked
    span can't be told apart from it and isn't scored.
    Drops below `threshold` (the node's daily swing) count as no response.
    `hourly_raw` must be UTC-indexed. Delays are from the unsmoothed hours."""
    level = hourly_raw.rolling(24, center=True, min_periods=12).median()
    rows = []
    starts = list(events.start[1:]) + [pd.Timestamp.max.tz_localize("UTC")]
    for e, next_start in zip(events.itertuples(), starts):
        if any(onset <= e.start <= peak + pd.Timedelta("12h") for onset, peak in blocked):
            continue
        stop = min([e.end + RESPONSE_WINDOW, next_start] + [onset for onset, _ in blocked if onset > e.start])
        before = hourly_raw[e.start - pd.Timedelta("24h"):e.start].median()
        after = level[e.start + pd.Timedelta("12h"):stop - pd.Timedelta("12h")].dropna()
        if after.empty:  # window under a day: fall back to hours after the rain
            after = hourly_raw[e.start:stop].rolling(6, min_periods=3).median().dropna()
        if np.isnan(before) or after.empty:
            continue
        drop = before - after.min()
        responded = drop > threshold
        hours = hourly_raw[e.start:stop].dropna()
        crossed = hours[before - hours > threshold]
        rows.append({
            "start": e.start, "end": e.end, "mm": e.mm, "peak_mm_h": e.peak_mm_h, "x_before": before,
            "drop": drop if responded else 0.0, "raw_drop": drop, "responded": bool(responded),
            "window_h": (stop - e.start).total_seconds() / 3600,
            "hours_to_first": (crossed.index[0] - e.start).total_seconds() / 3600 if responded and len(crossed) else np.nan,
            "hours_to_peak": (hours.idxmin() - e.start).total_seconds() / 3600 if responded else np.nan,
        })
    return pd.DataFrame(rows)


# --- Models ----------------------------------------------------------------------

def store_overflow(rain_h: pd.Series, et_h: pd.Series, s_top: float) -> pd.Series:
    """Hourly overflow (mm) from the top-layer store, starting empty."""
    et = et_h.reindex(rain_h.index).fillna(0.0).to_numpy()
    t, out = 0.0, np.zeros(len(rain_h))
    for k, r in enumerate(rain_h.to_numpy()):
        t += r
        if t > s_top:
            out[k] = t - s_top
            t = s_top
        t = t - et[k] if t > et[k] else 0.0
    return pd.Series(out, index=rain_h.index)


class Predictor:
    """Predicts each event's drop for one model variant."""

    def __init__(self, model: str, responses: pd.DataFrame,
                 rain_h: pd.Series, et_h: pd.Series, floor: float):
        self.model, self.rain_h, self.et_h = model, rain_h, et_h
        self.mm = responses["mm"].to_numpy()
        self.room = (responses["x_before"] - floor).clip(lower=0.0).to_numpy()
        # each event's hours in rain_h, for summing the store's overflow
        idx = rain_h.index
        self.spans = [(idx.searchsorted(s.floor("h")), idx.searchsorted(e.floor("h") + pd.Timedelta("1h")))
                      for s, e in zip(responses["start"], responses["end"])]

        self._cache: dict[float, np.ndarray] = {}

    def through(self, s_top: float = 0.0) -> np.ndarray:
        """mm per event that gets past the layer above the sensor."""
        if self.model == "none":
            return np.zeros_like(self.mm)
        if self.model == "linear":
            return self.mm
        if self.model == "threshold":
            return np.clip(self.mm - s_top, 0.0, None)
        key = round(s_top, 4)
        if key not in self._cache:
            over = store_overflow(self.rain_h, self.et_h, s_top).to_numpy()
            self._cache[key] = np.array([over[a:b].sum() for a, b in self.spans])
        return self._cache[key]

    def __call__(self, params: dict) -> np.ndarray:
        return np.minimum(params.get("gain", 0.0) * self.through(params.get("s_top", 0.0)), self.room)


S_TOP_GRID = np.round(np.arange(0.0, BOUNDS["s_top"][1] + 1e-9, 0.2), 4)


def fit(predictor: Predictor, observed: np.ndarray, mask: np.ndarray | None = None, seed: int = 0) -> dict:
    """Least-squares fit on the events in `mask`. With s_top fixed the drop
    is linear in gain (up to the floor clip), so: scan s_top on a 0.2 mm
    grid, solve gain by a bounded 1-D search for each, keep the best."""
    names = MODEL_PARAMS[predictor.model]
    mask = np.ones(len(observed), bool) if mask is None else mask
    if not names:
        return {}
    room, obs = predictor.room[mask], observed[mask]

    def best_gain(th):
        res = minimize_scalar(lambda g: np.mean((np.minimum(g * th, room) - obs) ** 2),
                              bounds=BOUNDS["gain"], method="bounded", options={"xatol": 1e-3})
        return float(res.x), float(res.fun)

    if "s_top" not in names:
        return {"gain": best_gain(predictor.through()[mask])[0]}
    best = min(((s_top, *best_gain(predictor.through(s_top)[mask])) for s_top in S_TOP_GRID),
               key=lambda t: t[2])
    return {"gain": best[1], "s_top": float(best[0])}


def leave_one_out(predictor: Predictor, observed: np.ndarray, seed: int = 0) -> np.ndarray:
    """Each event predicted by a fit that never saw it."""
    preds = np.empty(len(observed))
    for i in range(len(observed)):
        mask = np.ones(len(observed), bool)
        mask[i] = False
        preds[i] = predictor(fit(predictor, observed, mask, seed))[i]
    return preds
