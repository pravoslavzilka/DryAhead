"""Step 2 -- drying-window extraction.

Window start: the wettest point after rain stops and the sensor stops
moving further in the wet direction (an extremum found from the data, not
a fixed delay after rain). Window end: the next rain event that produces a
visible sensor response; small rain the sensor doesn't react to is
recorded (see `no_response` return value) but does not end the window.

Sign convention (which raw direction is "wetter") is determined
empirically per node -- see detect_sign_convention -- not assumed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..configs import window_thresholds as T


@dataclass
class RainEvent:
    start: pd.Timestamp
    end: pd.Timestamp
    total_mm: float


@dataclass
class Window:
    node_id: int
    start: pd.Timestamp
    end: pd.Timestamp
    start_value: float
    end_value: float
    termination_reason: str  # "rain" | "end_of_record"

    @property
    def duration_days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0


def find_rain_events(hourly_precip: pd.Series) -> list[RainEvent]:
    """hourly_precip: mm per hour, indexed by hour-start timestamp (UTC),
    sorted ascending. Merges wet hours separated by up to
    RAIN_EVENT_MERGE_GAP_HOURS of dry hours into a single event."""
    wet = hourly_precip[hourly_precip > 0]
    if wet.empty:
        return []
    merge_threshold = pd.Timedelta(hours=T.RAIN_EVENT_MERGE_GAP_HOURS + 1)
    events: list[RainEvent] = []
    cur_start = wet.index[0]
    cur_end = wet.index[0]
    cur_total = float(wet.iloc[0])
    for t, mm in wet.iloc[1:].items():
        if t - cur_end <= merge_threshold:
            cur_end = t
            cur_total += float(mm)
        else:
            events.append(RainEvent(cur_start, cur_end, cur_total))
            cur_start, cur_end, cur_total = t, t, float(mm)
    events.append(RainEvent(cur_start, cur_end, cur_total))
    return events


def _is_wetter(a: float, b: float, sign: int) -> bool:
    """True if raw value `a` represents wetter soil than `b`, given `sign`
    (-1: wetter = lower raw, +1: wetter = higher raw)."""
    return a < b if sign == -1 else a > b


def _wet_extremum_index(raw: np.ndarray, sign: int) -> int:
    return int(np.argmin(raw)) if sign == -1 else int(np.argmax(raw))


def detect_sign_convention(readings: pd.DataFrame, rain_events: list[RainEvent]) -> int:
    """Empirical sign convention: for the largest rain events (by total
    mm), compares the raw value just before the event to the most extreme
    raw value reached within RESPONSE_SEARCH_HOURS after it. If raw drops
    more than it rises, wetter = lower raw (typical for capacitive
    probes); majority vote across events breaks ties/noise from any one
    event. Prints the finding so it's visible in run logs.

    `readings`: columns ts (tz-aware, sorted ascending), raw -- one node.
    """
    if not rain_events:
        raise ValueError("no rain events in record; cannot determine sign convention")
    horizon = pd.Timedelta(hours=T.RESPONSE_SEARCH_HOURS)

    # Field nodes have real reporting gaps (weeks to months) -- the
    # biggest rain events *site-wide* frequently fall in a gap where this
    # particular node wasn't reporting. Rank by magnitude only among
    # events the node actually has before/after readings for, rather than
    # picking the top 5 globally and failing outright if none happen to
    # overlap this node's uptime (verified against live data: node 1's
    # top-5 site-wide events all fell in reporting gaps).
    candidates = []
    for ev in rain_events:
        before = readings[readings["ts"] <= ev.start]
        after = readings[(readings["ts"] > ev.start) & (readings["ts"] <= ev.end + horizon)]
        if before.empty or after.empty:
            continue
        candidates.append((ev, before, after))
    if not candidates:
        raise ValueError("could not locate readings around any rain event to determine sign convention")
    candidates.sort(key=lambda c: -c[0].total_mm)
    big_events = candidates[:5]

    votes: list[int] = []
    for ev, before, after in big_events:
        pre_value = before["raw"].iloc[-1]
        drop = pre_value - after["raw"].min()
        rise = after["raw"].max() - pre_value
        votes.append(-1 if drop > rise else 1)
    sign = -1 if votes.count(-1) >= votes.count(1) else 1
    label = "wetter = lower raw (capacitive-typical)" if sign == -1 else "wetter = higher raw"
    print(f"detect_sign_convention: {label} ({votes.count(sign)}/{len(votes)} of top rain events agree)")
    return sign


def find_windows(
    node_id: int, readings: pd.DataFrame, rain_events: list[RainEvent], sign: int
) -> tuple[list[Window], list[Window], list[dict]]:
    """readings: cleaned, sorted, columns ts/raw for one node.

    Returns (kept_windows, all_detected_windows, no_response) where
    kept_windows is all_detected_windows filtered to
    duration_days >= MIN_WINDOW_DAYS (report both, per spec: "Discard
    windows under ~5 days. Report window count per node before
    fitting."), and no_response lists rain events that didn't produce a
    visible sensor response (flagged, not treated as a window boundary).
    """
    ts = readings["ts"].reset_index(drop=True)
    raw = readings["raw"].reset_index(drop=True).to_numpy(dtype=float)
    # A plain np.searchsorted(ts.to_numpy(), np.datetime64(...)) breaks for
    # tz-aware timestamps: to_numpy() on a tz-aware Series yields an object
    # array of Timestamps (numpy has no tz-aware datetime64), and
    # np.datetime64(a_tz_aware_timestamp) silently drops the tz, so the two
    # sides become uncomparable. pd.DatetimeIndex.searchsorted compares
    # tz-aware Timestamps correctly.
    ts_index = pd.DatetimeIndex(ts)
    n = len(raw)

    all_windows: list[Window] = []
    no_response: list[dict] = []

    events = sorted(rain_events, key=lambda e: e.start)
    i_event = 0

    while i_event < len(events):
        ev = events[i_event]

        after_idx = int(ts_index.searchsorted(ev.end, side="right"))
        search_end = ev.end + pd.Timedelta(hours=T.RESPONSE_SEARCH_HOURS)
        search_idx = int(ts_index.searchsorted(search_end, side="right"))

        start_idx = None
        for j in range(after_idx, min(search_idx, n)):
            look_end = min(j + 1 + T.EXTREMUM_CONFIRM_READINGS, n)
            if look_end - (j + 1) < T.EXTREMUM_CONFIRM_READINGS:
                continue
            following = raw[j + 1:look_end]
            confirmed_drying = all(not _is_wetter(f, raw[j], sign) for f in following)
            is_extremum_so_far = _wet_extremum_index(raw[after_idx:look_end], sign) == (j - after_idx)
            if confirmed_drying and is_extremum_so_far:
                start_idx = j
                break

        if start_idx is None:
            i_event += 1
            continue

        window_start = ts.iloc[start_idx]
        start_value = raw[start_idx]

        end_idx = None
        termination = "end_of_record"
        j_event = i_event + 1
        while j_event < len(events):
            candidate = events[j_event]
            resp_search_end = candidate.end + pd.Timedelta(hours=T.RESPONSE_SEARCH_HOURS)
            lo = int(ts_index.searchsorted(candidate.start, side="left"))
            hi = int(ts_index.searchsorted(resp_search_end, side="right"))
            if lo >= n:
                break
            pre_value = raw[max(lo - 1, 0)]
            window_vals = raw[lo:min(hi, n)]
            if window_vals.size == 0:
                j_event += 1
                continue
            responded = (
                (pre_value - window_vals.min() >= T.MIN_RAW_RESPONSE_TO_END_WINDOW)
                if sign == -1
                else (window_vals.max() - pre_value >= T.MIN_RAW_RESPONSE_TO_END_WINDOW)
            )
            if responded:
                end_idx = lo
                termination = "rain"
                break
            no_response.append(
                {"node_id": node_id, "rain_start": candidate.start, "rain_end": candidate.end, "total_mm": candidate.total_mm}
            )
            j_event += 1

        if end_idx is None:
            end_idx = n - 1

        window_end = ts.iloc[end_idx]
        end_value = raw[end_idx]
        all_windows.append(Window(node_id, window_start, window_end, float(start_value), float(end_value), termination))

        i_event = j_event if end_idx != n - 1 else len(events)

    kept = [w for w in all_windows if w.duration_days >= T.MIN_WINDOW_DAYS]
    return kept, all_windows, no_response
