"""Site constants and parameter bounds for the FAO-56 bucket model.

Coordinates match frontend/src/hooks/useLocalWeather.js -- Zajezova, Slovensko,
the meteotekov.sk/@zajezova station -- so weather pulled here is at the same
point the frontend already shows the user.
"""

from __future__ import annotations

LAT = 48.453782
LON = 19.216477

# node_id -> real, calibrated field nodes (per sensor_calibration table).
# Rows with any other node_id in `readings` are cross-talk / test packets and
# are dropped during loading -- see data_supabase.filter_valid_nodes.
NODE_IDS = [1, 2, 3, 4, 5]

# Sensors report roughly every 20 minutes (contracts/telemetry.md); used to
# judge whether a day has enough coverage to trust its daily mean.
READING_CADENCE_MINUTES = 20
MIN_READINGS_PER_DAY = 20  # ~1/3 coverage floor before a daily mean is dropped

# --- Parameter bounds, per docs/model-design guidance --------------------
# (theta_fc, theta_wp, Zr, Kc, p, tau_d, runoff_frac, cal_a, cal_b)
#
# theta_fc / theta_wp: volumetric water content bounds spanning sand..clay.
# Zr: root zone depth in mm, 200-1500 per spec.
# Kc: crop coefficient, 0.3-1.4 per spec.
# p: readily-available-water depletion fraction, typically 0.4-0.6; bounded
#    a bit wider since orchard/vine root behaviour on this site is unmeasured.
# tau_d: drainage time constant in days for water above field capacity.
# runoff_frac: fixed fraction of rain that never infiltrates (simplest model
#    from the spec; SCS curve-number is the documented upgrade path once
#    per-node slope data exists).
# cal_a, cal_b: linear transform from the raw humidity proxy (0-1, from
#    sensor_calibration air/water endpoints) to physical theta -- the
#    "add two extra fitted parameters" escape hatch from the spec, used
#    because we have no oven-dry soil samples to calibrate theta properly.
BOUNDS = {
    "theta_fc": (0.10, 0.45),
    "theta_wp": (0.02, 0.35),
    "Zr": (200.0, 1500.0),
    "Kc": (0.3, 1.4),
    "p": (0.2, 0.8),
    "tau_d": (0.1, 10.0),
    "runoff_frac": (0.0, 0.6),
    "cal_a": (0.05, 0.60),
    "cal_b": (-0.10, 0.35),
}

# Parameters pooled (shared) across all nodes rather than fit per-node.
POOLED_PARAMS = ("Kc", "p")

# Parameters fit independently per node (site properties + this node's
# sensor calibration transform).
PER_NODE_PARAMS = ("theta_fc", "theta_wp", "Zr", "tau_d", "runoff_frac", "cal_a", "cal_b")

ALL_PARAMS = PER_NODE_PARAMS + POOLED_PARAMS

# Large finite penalty returned by the objective for physically invalid
# parameter draws (theta_wp >= theta_fc) instead of NaN/inf, which some
# scipy DE code paths handle poorly.
INVALID_PENALTY = 1e6

# Minimum theta_fc - theta_wp (TAW/Zr) gap treated as physically real. Below
# this, AWF = (theta-theta_wp)/(theta_fc-theta_wp) blows up numerically, and
# in practice a gap this small only shows up when the optimizer is
# underdetermined (too little data to pin down a real water-holding
# capacity) rather than describing an actual soil -- even sand's textbook
# fc-wp gap (~0.10) is well above this floor.
MIN_TAW_GAP = 0.04

# Chronological calibration/validation split.
CALIBRATION_FRACTION = 0.70

# Days to discard at the start of a simulation before scoring, so the fit
# isn't graded on the arbitrary initial condition (S0). 30 days is
# comfortable against a year of data; with only ~2 months of real deployment
# (the state of this project's data as of 2026-09), that would eat a third
# of the record, so this is deliberately shorter than the textbook default --
# still well beyond tau_d's bound (10 days) so the bucket has forgotten S0.
SPINUP_DAYS = 14

# A node needs at least this many observations *in the held-out validation
# window* before it's allowed to vote on the pooled (shared) Kc/p -- a node
# that goes dead before validation even starts can still calibrate fine
# in-sample, but nothing checks whether that fit generalizes, so it
# shouldn't get to set vegetation parameters imposed on nodes we *can*
# cross-check. Also the threshold validate.py uses to decide a node has
# "enough" held-out data to report metrics on at all.
MIN_VALIDATION_DAYS = 10

# Below this many scorable days, the objective returns INVALID_PENALTY
# outright rather than let differential_evolution fit noise (or find no
# signal at all and return an arbitrary, possibly out-of-order, parameter
# draw). 9 free parameters need meaningfully more than this to be trustworthy
# -- this is a floor against outright garbage, not a sufficiency guarantee.
MIN_SCORE_DAYS = 15

CACHE_DIR = "outputs"
