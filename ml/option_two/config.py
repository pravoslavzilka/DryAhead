"""Site/dataset constants for the option_two gradient-boosting pipeline.

Independent of ml/option_one/config.py -- not imported from it, per the
task brief (option_one and option_two are separate candidate approaches,
evaluated on their own merits). Values below were re-derived from the live
Supabase tables during this run (2026-09-04), not copied from option_one's
docstrings.
"""

from __future__ import annotations

# node_id -> real, calibrated field nodes, per the live sensor_calibration
# table (5 rows, node_id 1-5). Everything else seen in `readings` (0, 8, 9,
# 99 -- 29 rows total as of this run) is cross-talk/test traffic and is
# dropped in loaders.filter_valid_nodes.
NODE_IDS = [1, 2, 3, 4, 5]

# Sensors report ~every 20 minutes -> ~72 readings/day at full coverage.
# Used to judge whether a day has enough coverage to trust its daily
# aggregate. Set generously below full coverage since real days run well
# under 72 (gateway drops, node resets) without being untrustworthy.
MIN_READINGS_PER_DAY = 20

# --- Timestamp resolution -------------------------------------------------
# recorded_at is the node's own RTC; received_at is the server clock at
# ingest, always trustworthy. A live-data audit this run (see README "Data"
# section) found ml/option_one's ">2020" plausibility rule lets through
# rows where recorded_at is a stale/uninitialized RTC value that happens to
# land after 2020 -- e.g. one node-1 row reads recorded_at as 2024-04-24
# while its received_at is 2026-07-03; the RTC was simply wrong, not
# actually 2 years fast. Fix used here: for a *non-backlog* packet,
# recorded_at should read the current time -- if it disagrees with
# received_at by more than a generous clock-drift allowance, it's a clock
# fault, not a real timestamp, regardless of whether it's ">2020". A
# *backlog* packet (is_backlog=True, ~3% of rows) is a node replaying
# buffered readings written while it couldn't reach the gateway, so a large
# gap there is expected, not a fault -- observed backlog gaps in this data
# run up to ~37 days, so 90 days is a generous, non-tight ceiling.
MIN_PLAUSIBLE_EPOCH_STR = "2020-01-01"
NON_BACKLOG_MAX_GAP_SECONDS = 3600  # 1 hour: real-time packets, near-zero gap
BACKLOG_MAX_GAP_SECONDS = 90 * 86400  # 90 days: buffered/replayed packets

# Duplicate-packet detection (same physical transmission logged twice by a
# gateway retry / ingestion double-insert) -- exact match on this column set,
# keep earliest received_at. Verified still present in the live table this
# run: 8.8% of rows (vs. option_one's README's ~16% at an earlier point --
# see README "Data" section for why a lower rate here isn't a contradiction).
DEDUPE_KEY_COLUMNS = ["node_id", "raw", "temperature", "rssi", "snr"]

CACHE_DIR = "ingest/cache"
OUTPUTS_DIR = "outputs"

HORIZONS = [1, 7, 14, 28]
QUANTILE_ALPHAS = [0.1, 0.5, 0.9]

# Chronological split fraction for expanding-window CV's final holdout.
CV_MIN_TRAIN_DAYS = 21
CV_TEST_DAYS = 7

# LightGBM regularization -- per the task brief, deliberately tight for a
# dataset with very few independent drydown events.
GBM_PARAMS = dict(
    max_depth=5,
    min_child_samples=20,
    lambda_l2=1.0,
    feature_fraction=0.8,
    n_estimators=500,
    learning_rate=0.05,
    verbosity=-1,
)
EARLY_STOPPING_ROUNDS = 30

RAIN_THRESHOLD_MM = 1.0
ROLLING_WINDOWS = [3, 7, 14, 30, 60, 90]
