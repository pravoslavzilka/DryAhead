"""Cleaning thresholds for step 1 (data/clean.py).

Defaults below are conservative starting points reasoned from the sensor
spec (firmware ADC resolution, typical capacitive-probe swing), NOT tuned
against live data -- no code execution was available this session to pull
readings and inspect the effect of these values on real drydown curves.
See NIGHT_SUMMARY.md. Whoever runs this pipeline for the first time should
sanity-check the before/after plots in reports/ and adjust here -- this is
a config file specifically so that tuning never requires touching the
detection logic in data/clean.py.
"""
from __future__ import annotations

# --- 1. Range check ------------------------------------------------------
# ESP32 nodes call analogReadResolution(12) -- raw is a 12-bit ADC count,
# physically bounded to [0, 4095] regardless of what the soil is doing.
ADC_MIN = 0
ADC_MAX = 4095

# --- 2. Rate-of-change check ----------------------------------------------
# Flags a jump between consecutive readings (native ~20 min cadence) that
# is implausible for gradual soil drying/wetting when the weather record
# shows no rain in the preceding window. A capacitive probe's full
# air-to-water swing (sensor_calibration.air - .water) is typically a few
# hundred to ~1500 raw counts over the *entire* dry-to-wet range; a single
# 20-minute step covering a large fraction of that with no rain nearby is
# far more likely a packet glitch/ESD event than real soil movement.
MAX_RAW_DELTA_PER_READING = 250
RATE_CHECK_NO_RAIN_WINDOW_HOURS = 1.0

# --- 3. Robust local outlier detection (MAD) ------------------------------
LOCAL_OUTLIER_WINDOW_HOURS = 4.0    # rolling window, "a few hours" per spec
LOCAL_OUTLIER_MAD_MULTIPLIER = 5.0  # flag points >~5 MAD from local median

# --- 4. Temperature corroboration -----------------------------------------
# A jump at least this large in the temperature channel, at the same
# timestamp as an already-flagged moisture point, corroborates a real
# sensor/transmission glitch -- a genuine moisture change is gradual and
# has no accompanying temperature discontinuity.
TEMPERATURE_JUMP_THRESHOLD_C = 1.5

# --- 5. Short-run detection ------------------------------------------------
SHORT_RUN_MIN_LENGTH = 2   # readings
SHORT_RUN_MAX_LENGTH = 5   # readings
# A short run "reverts" if the reading immediately after it returns within
# this many raw counts of the level immediately before the run.
SHORT_RUN_REVERT_TOLERANCE_RAW = 30
