"""Thresholds for drying-window detection (events/windows.py).

Defaults below are starting points reasoned from the task spec, not tuned
against live data this session -- see NIGHT_SUMMARY.md.
"""
from __future__ import annotations

# Wet hours separated by a gap of at most this many dry hours are merged
# into one rain event, so one storm with a brief lull isn't split into
# several tiny "events". (Two wet-hour timestamps that are RAIN_EVENT_
# MERGE_GAP_HOURS of dry hours apart are exactly that many+1 hours apart,
# since hourly timestamps are 1 hour apart within a contiguous run.)
RAIN_EVENT_MERGE_GAP_HOURS = 2

# How far after a rain event's last wet hour to look for the sensor's own
# wettest point (candidate window start), and separately, for a "visible
# response" to a later rain event that would end a window.
RESPONSE_SEARCH_HOURS = 48

# A later rain event only ends a window if the sensor moves at least this
# many raw counts in the wet direction within RESPONSE_SEARCH_HOURS of it;
# smaller rain is recorded (events.windows.find_windows's `no_response`
# return value) but does not end the window.
MIN_RAW_RESPONSE_TO_END_WINDOW = 40

# How many consecutive readings after a candidate extremum must continue
# moving in the dry direction before that extremum is accepted as the
# window start -- guards against a single noisy tick masquerading as "the
# sensor stopped rising".
EXTREMUM_CONFIRM_READINGS = 3

# Discard windows shorter than this many days (task spec: "~5 days").
MIN_WINDOW_DAYS = 5.0
