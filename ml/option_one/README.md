# Option 1: physically-based FAO-56 bucket model

A single-bucket root-zone water balance, calibrated per node against real sensor
readings with differential evolution, scored by KGE. No machine learning --
the "learning" is six or seven physically-bounded parameters fit to match
observed drydown curves. See `docs/model-design/` for how this fits into the
platform's overall forecast approach; this folder is one candidate approach
(`option_one`), evaluated on its own merits against later options.

## Why a bucket model instead of a linear/ML fit

Rain-to-soil-moisture is strongly nonlinear: 30mm falling in one day mostly
runs off and drains away, while the same 30mm over a week mostly infiltrates.
The model tracks millimetres of water stored in the root zone (`theta * Zr`),
steps forward one **day** at a time (see "why daily, not weekly" below), and
applies, in order, each day:

1. **Rain** arrives, minus a fixed runoff fraction.
2. **Drainage** removes anything above field capacity, either instantly or
   with a time constant `tau_d` (more realistic for heavy soils).
3. **Plants and sun** remove `ETa = Ks * Kc * ET0`, where `Ks` is 1 while
   readily-available water remains and declines *linearly* to 0 at the
   wilting point once depletion passes `RAW = p * TAW`. That single kink is
   why real drydown curves bend and flatten instead of running straight to
   zero -- a linear model cannot reproduce it.

Full physics in `bucket_model.py`.

## Why daily steps, aggregated to weekly reporting

Aggregating weather to weekly averages *before* simulating destroys the
runoff/infiltration nonlinearity above. So: simulate at daily steps
(`bucket_model.simulate`), aggregate the daily *output* to weekly for
reporting. Run daily, report weekly.

## Pipeline

```
run_pipeline.py
  1. confirm Supabase access           (data_supabase.check_access)
  2. pull + dedupe sensor readings     (data_supabase.load_daily_theta_proxy)
  3. pull matching Open-Meteo history  (data_weather.fetch_historical_daily)
  4. calibrate per node                (calibrate.calibrate_all)
  5. validate vs. persistence          (validate.validate_node)
  6. ensemble forecast + AWF index     (forecast.forecast_node, forecast.summarize_forecast)
```

Run it: `python run_pipeline.py` (from this folder; needs `.env` -- see below).
Outputs land in `outputs/` (git-ignored): `fitted_params.json`,
`validation_report.json`, `equifinality_node<N>.csv`, `forecast_node<N>.csv`.

### 1. Data access

Confirmed before any modelling: this project's Supabase credentials live in
`frontend/.env` (`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`) and the same
project's anon key is used by `backend/reconciliation/.env` for server-side
scripts. `data_supabase.load_credentials()` reads `ml/option_one/.env` if
present (copy `.env.example`), and otherwise falls back to `frontend/.env`
directly, since it's the same anon key with the same read-only RLS scope
(`select` on `readings` and `sensor_calibration`). `check_access()` runs
first and fails fast with a clear message if that scope is missing.

### 2. Duplicates -- what's actually in the table

Auditing the live `readings` table (25,665 rows at the time of writing) found
two real data-quality issues, both handled in `data_supabase.py`:

- **~16% of rows are duplicate packets**: an exact match on
  `(node_id, raw, temperature, rssi, snr)` -- including a floating-point SNR
  -- appearing again minutes later under a different `id`/`received_at`.
  That's not two independent readings coincidentally matching on five
  fields; it's the same physical transmission logged twice (gateway retry or
  an ingestion double-insert). `dedupe_readings()` keeps the earliest
  `received_at` per exact-payload group and drops the rest.
- **Stray node IDs** (`0`, `8`, `9`, `99` -- 29 rows total) don't correspond
  to any calibrated field node and are dropped (`filter_valid_nodes`).
- `recorded_at` (the node's own RTC) is sometimes near-epoch (clock not yet
  synced) or drifts into the future. `resolve_timestamp()` mirrors the
  frontend's `readingTime()` (`frontend/src/lib/format.js`): trust
  `recorded_at` only if it's plausible (after 2020) and not later than
  `received_at`, otherwise fall back to the server clock.

### 3-4. Weather + calibration

`data_weather.py` pulls `precipitation_sum` and `et0_fao_evapotranspiration`
from Open-Meteo for the site coordinates (same lat/lon the frontend already
shows: Zajezova, Slovensko). Training and the eventual forecast both read
`et0_fao_evapotranspiration` from Open-Meteo -- deliberately the same
source, so calibration and inference never see systematically different ET0.

No oven-dried soil samples exist yet to calibrate raw ADC counts to true
volumetric `theta`, so `calibrate.py` fits two extra parameters per node
(`cal_a`, `cal_b`) mapping the sensor's `(air - raw) / (air - water)` proxy
(0-1) linearly onto physical `theta`, alongside the water-balance parameters.
This costs physical interpretability of the calibration transform itself,
but keeps `theta_fc` / `theta_wp` bounded in physically real ranges. If soil
samples become available later, replace the two-parameter transform with a
real fitted curve and drop `cal_a`/`cal_b` from the free parameters.

Optimization is `scipy.optimize.differential_evolution` (global, not
gradient descent -- the `Ks` kink makes the error surface non-convex),
scored by KGE (`metrics.kge`), not RMSE, so a well-timed-but-biased fit is
diagnosed as a bias problem rather than lumped into one number.

**Pooling is off by default.** The textbook argument (and the original
design note this folder started from) is that `Kc` and `p` are vegetation
properties and can be shared across nodes while `theta_fc`, `theta_wp`,
`Zr`, `tau_d`, `runoff_frac`, `cal_a`, `cal_b` stay per-node. That's only
true when the nodes actually sit under the same vegetation. This
deployment's five nodes are at different spots with different plant cover,
so forcing a shared `Kc`/`p` wouldn't average away that difference -- it
would push it into `theta_fc`/`theta_wp`/`Zr` instead, corrupting the site
parameters to compensate for a vegetation assumption that's wrong for part
of the site. So the default (`calibrate_all(..., pool_vegetation=False)`,
`run_pipeline.py`'s default) is every node fit **fully independently**, all
9 parameters. If per-node `theta_fc`/`theta_wp` (or `Kc`) come out very
different between nodes, that's not a bug -- it's a real measurement of how
heterogeneous the land and vegetation are.

Pooling remains available (`--pool-vegetation` / `pool_vegetation=True`) for
a future deployment (or a subset of nodes) that genuinely does share one
crop -- worth revisiting once there's enough per-node data that
independent fits are well-constrained on their own and pooling would only
be trading away accuracy you don't need to reduce variance you don't have.
When it's on, not every node gets a vote in the pooled median: a node whose
stage-A fit never converges to a physically valid parameter set is excluded
outright (`pool_shared`'s `valid` filter), and a node that fits fine
in-sample but died before the validation window opens is excluded too
(`calibrate.has_validation_coverage`) -- an unvalidated fit shouldn't get
equal say over parameters imposed on nodes that can actually be
cross-checked.

### 5. Validation

Chronological 70/30 split (`config.CALIBRATION_FRACTION`) -- never shuffled.
The calibration objective (`calibrate.make_objective`) only ever scores
against the first 70% of days; the simulation itself still runs continuously
through the full record, so the held-out tail is genuinely never touched by
the optimizer. Reported: KGE, RMSE (theta units), and the same two metrics
for a persistence baseline (tomorrow = today) at 1/3/7/14-day horizons.
Soil moisture has strong memory, so persistence is a hard baseline over
short horizons -- the model should beat it clearly by 7+ days. If it
doesn't beat it at all, that's the honest signal to stop before investing in
a heavier (option 2+) approach.

**Current status (run against live data, 2026-09-03)**: the model loses to
persistence at every horizon, on every node. This is a data-volume problem,
not a sign the physics is wrong -- the live record is only ~2 months deep
(nodes 1/4/5: 56 usable days from 2026-06-29 to 2026-09-02; node 3: 28 days;
node 2: 8 days, effectively dead), against 9 free parameters and a 70/30
split that leaves ~27 held-out days. `synthetic.py`'s self-test, given two full years of synthetic data, recovers
the underlying behaviour cleanly (calibration KGE > 0.95) -- so the pipeline
itself is sound; it's simply running ahead of the sensor deployment's actual
data volume right now. Re-run
`run_pipeline.py` as the record grows past a few months per node, and expect
this to flip once nodes clear a full wet/dry seasonal cycle.

### Equifinality

`calibrate.check_equifinality` reruns the optimizer from several random
seeds and reports each parameter's coefficient of variation. A parameter
with CV above ~0.2 isn't constrained by the data -- different, equally-valid
parameter sets fit the observed behaviour equally well, so that number
shouldn't be quoted as a measured soil property (it's still fine to use for
forecasting, since forecasting only needs the *combination* to reproduce
behaviour). `synthetic.py`'s self-test demonstrates this directly: recovers
`theta_fc`/`theta_wp` tightly but not `Zr`/`Kc`/`runoff_frac`, because a
shallower root zone with a higher crop coefficient removes water at nearly
the same rate as a deeper one with a lower coefficient. The fix, once
available: pin `theta_fc`/`theta_wp` from soil-texture lookups (Slovak soil
survey / a pedotransfer function) and `Zr` from the trees' actual rooting
depth, instead of leaving them all free.

### 6. Forecast

Once calibrated, `forecast.py` starts from the latest observed `theta` per
node and steps the bucket model forward once per Open-Meteo ensemble member
(`data_weather.fetch_forecast_ensemble`, ICON's ensemble by default --
`icon_seamless`, 40 members; pass `model="ecmwf_ifs025"` for ECMWF's 50
where your Open-Meteo plan allows it). The resulting spread across members
*is* a probability distribution over next month's soil-water state, with no
ML anywhere in the loop.

Raw `theta` is converted to **AWF** (Available Water Fraction, `forecast.awf`):

```
AWF = (theta - theta_wp) / (theta_fc - theta_wp)
```

1.0 = field capacity, 0.0 = wilting point, comparable across nodes with
different soils (raw `theta` is not). `summarize_forecast` also reports
`prob_below_wilting` per day -- the fraction of ensemble members that have
crossed the wilting point, which is the number a parametric-insurance
product would actually key off.

## Trying it before touching real data

`python synthetic.py` generates two years of data from known parameters and
refits them, printing fitted-vs-true parameters, held-out KGE/RMSE vs.
persistence, and the equifinality table -- a fast (no network) sanity check
that the model and optimizer are behaving before running the full pipeline
against Supabase + Open-Meteo.

## Known simplifications / next steps

- **Runoff** is a fixed fraction, not the SCS curve-number method the spec
  calls out as the "better version if your slopes are steep" -- there's no
  per-node slope/soil-group data yet to make curve numbers meaningful.
- **Sensor calibration** is the two-parameter linear-transform escape hatch,
  not oven-dried soil samples -- see "3-4. Weather + calibration" above.
- **Pooling** defaults to off (see "Pooling is off by default" above); when
  turned on for a genuinely single-vegetation deployment, it's two-stage
  (independent fit -> pool -> refit), not one joint optimization across all
  nodes and shared parameters at once.
- Ensemble forecast reforecast bias-correction isn't applied; Open-Meteo's
  raw ensemble spread is used as-is.
