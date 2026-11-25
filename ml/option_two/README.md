# Option 2: gradient-boosting soil-moisture forecast

A LightGBM-based direct multi-horizon forecaster, evaluated as a second,
independent candidate approach alongside `ml/option_one/` (the FAO-56
bucket model) -- see `ml/README.md` "Approaches". Not integrated with, and
does not import, `option_one`'s code.

## Persistence and water-balance-baseline comparison -- read this first

**Naming note before anything else:** this repo now has two unrelated
things both called "water balance," and they must not be conflated.
(1) `water_balance_{window}d` is a **feature** fed into this model --
just `rain_sum_w - et0_sum_w` over a rolling window, one input column
among 46. (2) The **water-balance baseline** discussed in this section is
a completely separate thing: `ml/option_one`'s full FAO-56 bucket-model
forecaster, run standalone and compared against this model's predictions.
Wherever this section says "water balance" without qualification, it
means (2), the baseline model -- never the feature.

**The water-balance baseline beats this gradient-boosting model at every
horizon, clearly, on genuinely held-out data.** That is a more important
and more humbling result than the persistence comparison below, and it's
stated here first rather than after: if you're choosing between
`option_one` and `option_two` today, at this data volume, `option_one`'s
physically-based model is currently the better choice.

| Horizon | Model RMSE (CV) | Persistence RMSE (CV) | Water-balance RMSE (held-out, n) | Model RMSE (LONO) | Persistence RMSE (LONO) | Water-balance RMSE (held-out, n) |
|---|---|---|---|---|---|---|
| h=1d  | 146.8 | 66.2  | **81.1** (n=78) | 134.8 | 116.8 | **81.1** (n=78) |
| h=7d  | 180.7 | 141.6 | **136.6** (n=57) | 319.8 | 328.9 | **136.6** (n=57) |
| h=14d | 394.7 | 199.6 | **157.1** (n=42) | 382.7 | 472.1 | **157.1** (n=42) |
| h=28d | 354.3 | 96.8  | **80.4** (n=6, too thin to trust) | 330.4 | 304.7 | **80.4** (n=6, too thin to trust) |

Water balance's CV and LONO numbers are identical at every horizon --
not a copy-paste bug, verified: once restricted to `date >= held-out
cutoff` (see next paragraph), CV's and LONO's test-row sets both reduce
to "every row on or after that date," which is the same row population
either way this dataset gets partitioned. `full_metrics.json` has MAE/KGE/NSE
alongside RMSE for both.

**Why "held-out" needed reconstructing, not just re-running:**
`option_one`'s bucket-model parameters (`option_one/outputs/fitted_params.json`)
were fit by differential evolution against the **first 70%** of each
node's record (`option_one/config.py`'s `CALIBRATION_FRACTION`). Scoring
those fixed parameters against rows from that same 70% would be scoring
the model on data it was fit to reproduce -- not a real test, unlike
persistence (fits nothing) or this model (proper CV/LONO on data it never
trains on). `eval/baselines.water_balance_held_out_cutoff` reconstructs
option_one's shared cutoff date (2026-08-05, cross-checked against
`option_one/outputs/validation_report.json`'s 28 held-out days for node
1, whose record ends 2026-09-02 -- exact match) and every number in the
table above is restricted to dates at or after it. The unrestricted
(in-sample-included) numbers are lower still and are in
`full_metrics.json` as `*_water_balance_all` -- not headlined here
because they'd overstate the comparison.

**In chronological (expanding-window) CV, this model does not beat
persistence at any horizon.** In leave-one-node-out (the harder, more
relevant test for a new-site deployment), it beats persistence at h=7
(RMSE 319.8 vs. 328.9 -- a marginal win) and clearly at h=14 (RMSE 382.7
vs. 472.1), but not at h=1 or h=28. And at every horizon in both CV and
LONO, it loses to the water-balance baseline above by a wide margin --
this model doesn't just fail to clearly beat a naive rule, it's currently
worse than a fixed physical model that has zero features and 7-9
hand-fit parameters.

| Horizon | CV rows (model / persist.) | CV: model RMSE | CV: persistence RMSE | Model beats persistence (CV)? | LONO rows | LONO: model RMSE | LONO: persistence RMSE | Model beats persistence (LONO)? |
|---|---|---|---|---|---|---|---|---|
| h=1d  | 99  | 146.8 | 66.2  | **no** | 191 | 134.8 | 116.8 | **no** |
| h=7d  | 57  | 180.7 | 141.6 | **no** | 141 | 319.8 | 328.9 | **marginal yes** |
| h=14d | 54  | 394.7 | 199.6 | **no** | 110 | 382.7 | 472.1 | **yes** |
| h=28d | 6   | 354.3 | 96.8  | **no (data too thin to trust either number)** | 54  | 330.4 | 304.7 | **no** |

RMSE is in raw ADC counts (see "Why raw ADC, not calibrated theta" below;
not a physical unit, not comparable across sensors with different
air/water calibration endpoints without more work -- the water-balance
baseline's predictions *are* converted to this same unit, using
`option_one`'s own already-fitted air/water/cal_a/cal_b calibration
purely as a unit conversion for this comparison; see
`eval/baselines.water_balance_raw_series`'s docstring). Full
RMSE/MAE/KGE/NSE for every comparison at every horizon:
`outputs/full_metrics.json`.

**h=28's CV number is not meaningful and shouldn't be read as a real
comparison** -- only 2 expanding-window folds exist at that horizon
(6 test rows total), a direct consequence of the dataset's length (see
"Effective sample size" below), not a modeling choice. LONO's 54 rows at
h=28 (from 3 of 5 nodes -- 2 don't have enough record depth to produce any
h=28 target at all) is the only h=28 number worth any weight, and it also
loses to persistence.

**Answering the brief's specific question:** does the model beat
persistence at h=14 and h=28? **h=14: yes under leave-one-node-out, no
under chronological CV. h=28: no under either.** And at both horizons it
loses to the water-balance baseline regardless. This is reported plainly,
not spun -- per the task brief, "if it doesn't beat persistence at a
given horizon, say so plainly in the report."

Given h=1 persistence being nearly unbeatable is expected (the brief said
so up front) and matches what happened here, that part isn't a concern.
The concerning part is CV losing at every horizon including h=14, where
LONO says the model should win -- see "Why CV and LONO disagree" below --
and losing to the water-balance baseline everywhere, which no amount of
CV/LONO disagreement explains away.

## Effective sample size -- the number that matters more than row counts

| Node | Calendar-day rows | Effective independent wetting events |
|---|---|---|
| 1 | 68 | 11 |
| 2 | 41 | 9 |
| 3 | 28 | 7 |
| 4 | 68 | 11 |
| 5 | 68 | 11 |
| **Total** | **273** | **49** |

"Effective independent wetting events" = number of times a node's
`days_since_rain` resets to 0 after having been > 0 (i.e. a transition
from a dry run into a rain day) -- see `eval/report.py`'s
`effective_event_count` docstring for the exact, auditable definition.
This is a proxy for "distinct drydown cycles the model could possibly
learn from," not a formal hydrological event-separation algorithm. **49
independent events, most of them at a single small hillside site, is the
real sample size this pipeline is working with -- not 273 rows, and
nowhere near enough to trust CV-vs-LONO disagreements or per-horizon SHAP
rankings as stable.**

## Why CV and LONO disagree

Chronological CV's folds are short (7-day test windows) and few (2-6
folds depending on horizon) because the deployment record itself is only
~2 months deep. A single unusual week (a heavy, off-pattern storm; a
sensor glitch day that survived the `n_readings` coverage floor) can swing
an entire fold's RMSE. LONO pools far more test rows per horizon (54-191
vs. 6-99) by testing whole nodes at once, so it's less sensitive to any
one calendar week, but it answers a different question (does this
generalize to an unseen *site*, not does this generalize to an unseen
*future date*) -- both are asked in the brief, and they legitimately
disagree here rather than one being "the real answer." Read the table
above with that in mind, not as one number picked from the two.

## Data

### Live schema, as found in this run (2026-09-04)

`readings` columns: `id, node_id, raw, temperature, recorded_at, rssi,
snr, is_backlog, received_at`. `sensor_calibration` columns: `node_id,
air, water, dry_soil, wet_soil, updated_at, GPS`.

- **Node count: 5, not 4.** The original brief said "four deployed sensor
  nodes"; `sensor_calibration` has exactly 5 rows (node_id 1-5), each with
  a distinct GPS coordinate. `readings.node_id` also contains 0, 8, 9, 99
  (29 rows total) -- cross-talk/test traffic, dropped.
- **Node coverage is very uneven.** Node 1/4/5: 56 usable days each
  (2026-06-29..2026-09-04). Node 3: 28 days (2026-06-29..2026-07-26, then
  silent). Node 2: 8 usable days (2026-06-29..2026-08-08) -- effectively
  dead early in the record.
- **`is_backlog` exists and matters.** ~3% of rows (824/26210) are marked
  `is_backlog=True` -- a node replaying readings it buffered while it
  couldn't reach the gateway, sometimes up to ~37 days late. Not fetched by
  `ml/option_one/data_supabase.py`; fetched and used here (see "Real
  timestamp bug fixed" below).
- **Per-node GPS is real and used.** Each node's own `sensor_calibration.GPS`
  is parsed and used to fetch that node's own Open-Meteo weather (and
  elevation), rather than one shared site coordinate the way
  `ml/option_one/` does. In practice the 5 nodes are close enough (same
  hillside, <0.003 degrees apart) that the daily weather variables come
  back effectively identical across nodes at Open-Meteo's grid resolution
  -- so this mostly matters for **elevation** (which does differ slightly
  node to node: 648-669 m, see "Static per-node attributes" below), not
  for rain/temperature/ET0.

### Real data-quality bug found and fixed (not present in `option_one`)

`ml/option_one/data_supabase.py`'s timestamp-resolution rule trusts
`recorded_at` (the node's own RTC) whenever it's `>= 2020-01-01` and not
after `received_at`. Auditing the live table found this isn't tight
enough: one node-1 row has `recorded_at` decoding to **2024-04-24** while
its `received_at` (the reliable server clock) is **2026-07-03** -- a stale/
uninitialized RTC value that happens to be a plausible-looking date, not a
real timestamp. It passes `option_one`'s `>2020` check anyway.

Fixed here (`config.py` / `ingest/loaders.py resolve_timestamp`) by adding a
gap check keyed on `is_backlog`: a **non-backlog** packet's `recorded_at`
must be within 1 hour of `received_at` (real packets in this data are
essentially real-time -- the 99th percentile gap among non-backlog rows is
~0 seconds) or it's treated as a clock fault and `received_at` is used
instead; a **backlog** packet gets a 90-day allowance (observed real
backlog gaps top out around 37 days). Of 26210 raw rows, only ~78 non-
backlog rows had a gap over 2 days -- a small, specific set of bad RTC
reads, not a systemic issue, but real: without this fix, node 1's usable
date range appeared to include a phantom outlier day in 2024.

### Duplicate packets -- still present, similar shape to `option_one`'s finding

Exact-match duplicates (same `node_id, raw, temperature, rssi, snr`,
different `id`/`received_at`) -- kept earliest `received_at`, dropped the
rest: **8.8%** of rows this run (2305/26181, after dropping stray node
IDs), vs. `option_one/README.md`'s ~16% "at the time of writing" (an
earlier, smaller table). A lower rate now isn't a contradiction -- it's
consistent with the same absolute duplicate-generating behavior against a
table that's grown substantially since (26210 rows now vs. 25665 then).

### Soil moisture: why raw ADC, not calibrated theta

`readings.raw` is the sensor's raw capacitive ADC reading. `sensor_calibration`
has `air`/`water` (and also `dry_soil`/`wet_soil`, unused here) reference
endpoints that `option_one` uses to build a linear 0-1 "humidity proxy" --
that's a calibration transform, even though it's not one this pipeline
invented. Per the brief's explicit instruction ("if raw, keep it raw and
model it directly -- do not invent a calibration curve"), **this pipeline
models `readings.raw` directly, unscaled.** `raw` is inversely related to
moisture given this sensor's endpoints (`water` ~1700-1760 < `air`
~3140-3210): raw drops as soil gets wetter. `target_h{n} = raw[t+n] -
raw[t]`, so a negative target means the sensor got wetter over the
horizon, not drier -- easy to misread, called out here explicitly.

A live-data check found ~0.1-9% of raw readings per node fall outside
`[min(air,water), max(air,water)]` (worst: node 4 at 9.2%) -- glitch
reads, not filtered out here (the brief asks to model raw directly, not to
clean it further); they're averaged into `raw_mean` along with everything
else for the day, diluted but not removed. Noted as a real, unaddressed
noise source, not invented-away.

### Static per-node attributes

The brief asks for slope/aspect/elevation if available. Slope and aspect:
**not available anywhere in this repo** -- skipped, not invented.
Elevation: **available**, from Open-Meteo's own response for each node's
GPS coordinate (648-669 m across the 5 nodes) -- included as
`elevation_m`. With only 5 nodes, LightGBM's `node_id` categorical split
already captures per-node identity more directly than a near-constant
numeric elevation column does, so don't expect `elevation_m` to carry much
independent signal (SHAP confirms this -- see below).

## Feature table

One row per node-calendar-day (not just days with a sensor reading --
gap days are included as all-NaN rows, both to keep lag/rolling windows
date-correct and because LightGBM handles missing feature values natively,
no imputation needed). Full column list: `ingest/features.py`'s
`FEATURE_COLUMNS`. Built per the brief's list exactly: lagged moisture
(t-1/2/3/7/14), lagged precipitation (t-1/2/3), rolling rain/ET0 sums and
their difference (3/7/14/30/60/90 days), days since last >1mm rain,
rolling mean/max temperature and VPD (7/30 days, VPD via the Tetens
saturation-vapor-pressure formula from mean daily temp + mean RH),
day-of-year sin/cos, node ID, and elevation.

**Rolling windows are computed on weather extended `max(window)=90` days
before each node's own moisture record starts** (fetched separately, not
trimmed to the moisture span before rolling), so the model's very first
usable row per node can still have a real 90-day-back sum instead of a
silently-partial one. `tests/test_features.py::test_rolling_windows_require_full_history`
checks this doesn't regress into a truncated-window bug.

## Leakage

Every feature column is computed from data at or before its own row's
date; only the `target_h*` columns look ahead, and only as training
labels, never as inputs. `tests/test_features.py::test_no_feature_uses_future_moisture`
plants a synthetic future spike and asserts every feature before the spike
date is bit-for-bit identical whether or not the spike exists downstream
-- paired with `test_target_horizon_does_use_future_moisture`, which
confirms the same spike *does* change the target (so the first test isn't
vacuously passing because nothing in the table ever changes).

## Model

LightGBM installed cleanly in this environment -- no sklearn fallback
needed. Direct multi-horizon (a separate model per h in {1,7,14,28}, each
trained straight on `target_h{h}`), not recursive -- no rollout, no
compounding-error failure mode to guard against. Regularization per the
brief: `max_depth` 4 (h=14/28, the more data-starved horizons) or 5
(h=1/7), `min_child_samples`=20, `lambda_l2`=1.0, `feature_fraction`=0.8,
early stopping on a chronological validation tail. Mean model +
quantile models at alpha 0.1/0.5/0.9 for every horizon (`objective=
"quantile"`), so `predict.py` returns an interval, not a point estimate.

## SHAP -- what's driving the predictions

`outputs/shap_h{1,7,14,28}.png`, importances in
`outputs/shap_importance.json`. **`node_id` has exactly zero SHAP
importance at every horizon** (rank last of 46 features, mean |SHAP| =
0.000) -- the model is not relying on node identity as a shortcut. What it
does rely on, by horizon:

- h=1: `wind_speed_10m_max` dominates, then `water_balance_14d` -- wind
  driving next-day evaporative loss is plausible but not the first feature
  expected to lead; worth treating skeptically given only 4 features have
  any signal at all here (see below).
- h=7: `temp_mean_7d` dominates heavily, then lagged moisture -- physically
  sensible (temperature drives evapotranspiration over a week).
- h=14 and h=28: `rain_sum_14d` dominates, alone accounting for nearly all
  signal at h=28 -- the single most physically sensible result in this
  whole table (accumulated rainfall is exactly what should drive moisture
  change over 2-4 weeks).

**Caveat that applies to all of the above:** with regularization this
tight against a dataset this small, only 1-4 features out of 46 have
*any* nonzero SHAP importance at a given horizon (down to just 1 at h=28).
These trees are close to stumps. Reading a ranked-importance list from
this as "the model has learned X" overstates what a handful of splits on
49 effective events can support -- it's evidence the model isn't leaning
on something obviously wrong (node ID), not proof it has learned real
physical structure.

## Deliverables

```
ml/option_two/
  config.py               site/dataset constants
  ingest/loaders.py        Supabase + Open-Meteo fetch, disk-cached (ingest/cache/, gitignored)
  ingest/features.py        lag/rolling feature table + leakage-safe construction
  modeling/gbm.py           direct multi-horizon training, expanding-window CV, leave-one-node-out
  eval/metrics.py           RMSE, MAE, KGE, NSE
  eval/baselines.py         persistence
  eval/report.py            effective-event count, evaluation orchestration, plots
  configs/h{1,7,14,28}.yaml per-horizon config (mirrors config.py's defaults)
  train.py                  CLI entry point -- python train.py
  predict.py                load saved models + latest data -> prediction interval per node/horizon
  requirements.txt          pinned to what's actually installed in this run
  tests/test_features.py    leakage + rolling-window + lag-shift regression tests
  NIGHT_SUMMARY.md
```

Run: `pip install -r requirements.txt && python train.py` (needs
`ml/option_two/.env` or `frontend/.env` for Supabase credentials, network
access to Supabase + Open-Meteo). Outputs (models, plots, metrics,
feature table) land in `outputs/`, gitignored.

## Known limitations

- `predict.py` does not itself call Open-Meteo's forecast endpoint. Every
  feature in this table is backward-looking by construction (lags/rolling
  windows of *past* data as of day t), which is what keeps the model
  leakage-free and genuinely "direct" -- so predicting h days ahead only
  needs today's real feature row, not a forecast of the next h days of
  weather. `ingest/loaders.py fetch_forecast_daily` exists and works
  (smoke-tested against the live API during this run) but isn't wired into
  `predict.py`, since nothing in the trained feature set would consume it.
  If a future iteration adds forward-looking weather features, this is the
  seam to extend.
- ~~No third baseline against `ml/option_one/bucket_model.py`~~ -- added
  in a follow-up pass (see "Persistence and water-balance-baseline
  comparison" up top): reuses `option_one`'s *already-fitted*
  `outputs/fitted_params.json` read-only rather than re-running its
  differential-evolution calibration, so it stayed a bounded addition. The
  result: the water-balance baseline beats this model at every horizon.
- Raw-ADC glitch reads (0.1-9% of readings per node, outside the
  `[water, air]` calibration range) are averaged into daily means, not
  filtered -- see "Soil moisture" above.
