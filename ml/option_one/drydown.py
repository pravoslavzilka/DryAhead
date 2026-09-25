"""Drying model: how a node's raw soil reading rises (dries) between wettings,
driven by the station's evaporative demand. No rain anywhere in it -- rain
belongs to a separate wetting model, still to be built.

Works in raw ADC counts per node (higher = drier on these sensors: `air` ~3140-
3210 > `water` ~1710-1760). Raw can always be converted to % later; % is
clamped at 0/100 and can't be converted back.

Each day, from today's observed/simulated reading x:

  1. Drainage. Wetter than field capacity (x < raw_fc)? The excess drains
     with time constant tau_d:     x += (raw_fc - x) * (1 - exp(-1/tau_d))
  2. Stress factor Ks. Depletion D = x - raw_fc (0 if wetter than raw_fc);
     TAW = raw_wp - raw_fc; RAW = p * TAW.
         Ks = 1                        while D <= RAW
         Ks = (TAW - D) / (TAW - RAW)  after that, reaching 0 at raw_wp
  3. Weather-driven drying:        x += Ks * (a * rad_mm + b * aero_mm)

  rad_mm / aero_mm are the sun and air-drying halves of Penman-Monteith
  (station_weather.py). `a`/`b` (counts per mm) say how strongly each drives
  drying at this node. With split=False they're tied (a == b), which is plain
  ET0 x one rate -- the 5-parameter baseline the split is compared against.

This is the FAO-56 bucket model's loss half (bucket_model.py) rewritten in
the sensor's own units. Kc, Zr and the %->theta scale only ever appear as one
product while drying, so they're folded into a/b instead of fitted apart.

Drying segments are cut from the node's own readings, not station rain:
station rain and node wetting don't line up one-to-one (showers that missed
the station wetted nodes 1/4; rain under ~3 mm never reached nodes 4/5).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

PARAM_NAMES = ("raw_fc", "raw_wp", "p", "tau_d", "a", "b")
MIN_TAW_COUNTS = 50  # raw_wp - raw_fc below this isn't a real soil, it's the optimizer failing
INVALID_PENALTY = 1e6

MIN_READINGS_PER_DAY = 20  # ~1/3 of the 72 readings a node sends per day
MIN_SEGMENT_DAYS = 3
HORIZONS_DAYS = (1, 3, 7, 14)


@dataclass
class DrydownParams:
    raw_fc: float
    raw_wp: float
    p: float
    tau_d: float
    a: float
    b: float


def simulate(x0: float, rad: np.ndarray, aero: np.ndarray, prm: DrydownParams) -> np.ndarray:
    """Readings for day 0..n from x0 and n daily forcings. Same length+1 as rad."""
    fc, wp = prm.raw_fc, prm.raw_wp
    taw = wp - fc
    raw_thr = prm.p * taw
    drain = 1.0 - np.exp(-1.0 / prm.tau_d)
    out = [float(x0)]
    x = float(x0)
    for r, e in zip(rad.tolist(), aero.tolist()):
        if x < fc:
            x += (fc - x) * drain
        depletion = x - fc if x > fc else 0.0
        if depletion <= raw_thr:
            ks = 1.0
        else:
            ks = (taw - depletion) / (taw - raw_thr)
            ks = 0.0 if ks < 0.0 else ks
        demand = prm.a * r + prm.b * e
        prev = x
        x += ks * (demand if demand > 0.0 else 0.0)
        if x > wp and prev <= wp:  # a large step can't carry it past the wilting point
            x = wp
        out.append(x)
    return np.asarray(out)


# --- From readings to daily series and drying segments ----------------------

def hourly_and_daily(readings: pd.DataFrame, tz: str) -> tuple[pd.Series, pd.Series]:
    """One node's readings -> (hourly median raw, daily median raw on local days).
    Days with fewer than MIN_READINGS_PER_DAY readings are NaN."""
    s = readings.set_index(readings["ts"].dt.tz_convert(tz))["raw"].sort_index()
    hourly = s.resample("1h").median()
    daily = s.resample("1D").agg(["median", "size"])
    daily = daily["median"].where(daily["size"] >= MIN_READINGS_PER_DAY)
    daily.index = daily.index.tz_localize(None)
    return hourly, daily


def wetting_threshold(hourly: pd.Series) -> float:
    """Smallest rise treated as real wetting: the node's typical daily
    up/down swing (it reads driest ~15:00, wettest ~20-22:00 local), or 3x
    hour-to-hour noise if larger. Median over all days, so the minority of
    rain days barely moves it."""
    h = hourly.dropna()
    detrended = (h - h.rolling(25, center=True, min_periods=12).mean()).dropna()
    per_day = detrended.groupby(detrended.index.date)
    swing = per_day.agg(lambda x: x.max() - x.min())[per_day.size() >= 20].median()
    noise = 3 * 1.4826 * h.diff().abs().median()
    return float(max(swing, noise))


def detect_wettings(hourly: pd.Series, threshold: float) -> list[dict]:
    """Wetting episodes: raw falls by more than `threshold` within 6 hours and
    is still lower a day later (so the daily cycle and one-off blips don't
    count). Returns [{onset, peak, size}], peak = wettest hour within 48 h."""
    h = hourly.interpolate(limit=2)
    fall = h.rolling(7, min_periods=4).max() - h
    hits = fall[fall > threshold]
    if hits.empty:
        return []
    groups = (hits.index.to_series().diff() > pd.Timedelta("12h")).cumsum()
    episodes = []
    for _, grp in hits.groupby(groups.values):
        onset = grp.index[0]
        before = h[onset - pd.Timedelta("7h"):onset - pd.Timedelta("5h")].median()
        later = h[onset + pd.Timedelta("22h"):onset + pd.Timedelta("26h")].median()
        if not np.isnan(later) and not np.isnan(before) and later > before - threshold / 2:
            continue  # recovered within a day -- not a wetting the soil kept
        window = h[onset:onset + pd.Timedelta("48h")]
        episodes.append({"onset": onset, "peak": window.idxmin(), "size": float(grp.max())})
    return episodes


def detect_slow_wettings(daily: pd.Series, threshold: float, tz: str) -> list[dict]:
    """Wettings spread over 2-3 days that detect_wettings' 6-hour window
    misses -- node 1 took ~38 h to respond to 09-11's rain, and got wetter
    by ~70 counts over 08-24..08-27 with no station rain at all. A daily
    median more than `threshold` below the wettest of the previous 3 days,
    and still wetter the next day, marks one. Same {onset, peak, size} shape."""
    d = daily.dropna()
    episodes = []
    for i in range(3, len(d) - 1):
        prev = d.iloc[i - 3:i]
        fall = prev.max() - d.iloc[i]
        if fall > threshold and prev.max() - d.iloc[i + 1] > threshold / 2:
            onset = prev.idxmax() + pd.Timedelta(days=1)
            window = d[d.index[i]:d.index[i] + pd.Timedelta(days=3)]
            episodes.append({"onset": onset.tz_localize(tz), "peak": window.idxmin().tz_localize(tz), "size": float(fall)})
    return episodes


def build_segments(daily: pd.Series, wettings: list[dict], start: str, end: str | None = None) -> list[pd.Series]:
    """Split the daily series into drying segments: each runs from the first
    full day after a wetting's peak to the last full day before the next
    wetting's onset. Segments shorter than MIN_SEGMENT_DAYS observed days
    are dropped."""
    daily = daily[start:end] if end else daily[start:]
    cuts = sorted(
        (pd.Timestamp(w["onset"].date()), pd.Timestamp(w["peak"].date()) + pd.Timedelta(days=1))
        for w in wettings
    )
    segments, seg_start = [], daily.index.min()
    for onset_day, resume_day in cuts + [(daily.index.max() + pd.Timedelta(days=1), None)]:
        seg = daily[seg_start:onset_day - pd.Timedelta(days=1)]
        first = seg.first_valid_index()
        if first is not None:
            seg = seg[first:]
            if seg.notna().sum() >= MIN_SEGMENT_DAYS:
                segments.append(seg)
        if resume_day is not None:
            seg_start = max(seg_start, resume_day)
    return segments


def split_segments(segments: list[pd.Series], split_day: pd.Timestamp) -> tuple[list, list]:
    """Chronological calibration/validation split; a segment spanning the
    split is cut in two, the later part restarting from its observed value."""
    cal, val = [], []
    for seg in segments:
        for part, bucket in ((seg[:split_day - pd.Timedelta(days=1)], cal), (seg[split_day:], val)):
            first = part.first_valid_index()
            if first is not None and part[first:].notna().sum() >= MIN_SEGMENT_DAYS:
                bucket.append(part[first:])
    return cal, val


# --- Fitting ----------------------------------------------------------------

def forcing(seg: pd.Series, weather: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Weather driving the step from day i to day i+1. A daily median sits
    around midday, so each step spans half of each day: average the two."""
    w = weather.reindex(seg.index)
    rad, aero = w["rad_mm"].to_numpy(), w["aero_mm"].to_numpy()
    return (rad[:-1] + rad[1:]) / 2, (aero[:-1] + aero[1:]) / 2


def _params_from(x: np.ndarray, split: bool) -> DrydownParams:
    raw_fc, raw_wp, p, tau_d, a = x[:5]
    return DrydownParams(raw_fc, raw_wp, p, tau_d, a, x[5] if split else a)


def bounds_for(air: float, water: float, split: bool) -> list[tuple[float, float]]:
    counts = (water - 200, air + 200)
    b = [counts, counts, (0.05, 0.95), (0.1, 10.0), (0.0, 60.0)]
    return b + [(0.0, 60.0)] if split else b


def make_objective(segments: list[pd.Series], weather: pd.DataFrame, split: bool):
    """RMSE (counts) of each segment simulated open-loop from its first
    observed day -- the same thing a forecast from the latest reading does."""
    prepared = []
    for seg in segments:
        rad, aero = forcing(seg, weather)
        obs = seg.to_numpy()
        prepared.append((obs[0], rad, aero, obs[1:], ~np.isnan(obs[1:])))
    n_scored = sum(int(m.sum()) for *_, m in prepared)

    def objective(x: np.ndarray) -> float:
        prm = _params_from(x, split)
        if prm.raw_wp - prm.raw_fc < MIN_TAW_COUNTS:
            return INVALID_PENALTY
        sq = 0.0
        for x0, rad, aero, obs, mask in prepared:
            sim = simulate(x0, rad, aero, prm)[1:]
            sq += float(np.sum((sim[mask] - obs[mask]) ** 2))
        return float(np.sqrt(sq / n_scored))

    return objective


def fit(segments, weather, air, water, split=True, seed=0, maxiter=300, popsize=20) -> dict:
    result = differential_evolution(
        make_objective(segments, weather, split), bounds_for(air, water, split),
        seed=seed, maxiter=maxiter, popsize=popsize, tol=1e-8, mutation=(0.5, 1.5),
        recombination=0.7, polish=True, updating="deferred",
    )
    prm = _params_from(result.x, split)
    return {"params": vars(prm), "rmse": float(result.fun), "valid": result.fun < INVALID_PENALTY / 2}


def check_equifinality(segments, weather, air, water, split=True, n_starts=8, base_seed=1000, maxiter=300, popsize=20) -> pd.DataFrame:
    """Refit from several random starts. A parameter whose spread across
    equally good fits is more than 10% of its allowed range isn't pinned
    down by this data -- the curve fits, but don't read that number as a
    property of the soil."""
    names = PARAM_NAMES if split else PARAM_NAMES[:5]
    runs = pd.DataFrame([
        fit(segments, weather, air, water, split, seed=base_seed + i, maxiter=maxiter, popsize=popsize)["params"]
        for i in range(n_starts)
    ])[list(names)]
    width = pd.Series([hi - lo for lo, hi in bounds_for(air, water, split)], index=list(names))
    summary = pd.DataFrame({"mean": runs.mean(), "min": runs.min(), "max": runs.max()})
    summary["spread_of_range"] = (summary["max"] - summary["min"]) / width
    summary["well_constrained"] = summary["spread_of_range"] < 0.10
    return summary


# --- Evaluation -------------------------------------------------------------

def horizon_errors(segments, weather, prm: DrydownParams | None, drift_per_day: float) -> pd.DataFrame:
    """Forecast from every observed day in every segment to each horizon
    inside that segment, for three predictors:
      model       -- this drying model, started from the observed reading
      persistence -- reading stays where it is
      drift       -- reading rises by the calibration period's average daily drying
    Returns long-form rows [horizon, predictor, error]."""
    rows = []
    for seg in segments:
        obs = seg.to_numpy()
        rad, aero = forcing(seg, weather)
        for i in np.where(~np.isnan(obs))[0]:
            sim = simulate(obs[i], rad[i:], aero[i:], prm) if prm else None
            for h in HORIZONS_DAYS:
                j = i + h
                if j >= len(obs) or np.isnan(obs[j]):
                    continue
                preds = {"persistence": obs[i], "drift": obs[i] + h * drift_per_day}
                if sim is not None:
                    preds["model"] = sim[h]
                rows += [{"horizon": h, "predictor": k, "error": v - obs[j]} for k, v in preds.items()]
    return pd.DataFrame(rows)


def mean_daily_drift(segments) -> float:
    steps = pd.concat([seg.diff() for seg in segments]).dropna()
    return float(steps.mean()) if len(steps) else 0.0


def rmse_table(errors: pd.DataFrame) -> pd.DataFrame:
    if errors.empty:
        return pd.DataFrame()
    g = errors.groupby(["horizon", "predictor"])["error"]
    return pd.DataFrame({"rmse": g.apply(lambda e: float(np.sqrt(np.mean(e ** 2)))), "n": g.size()}).unstack("predictor")
