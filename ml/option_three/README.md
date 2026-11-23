# Option three: physically-parameterized soil-drydown calibration

## Status, up front

**No node is calibrated. No window counts exist. No persistence
comparison exists.** Not because the data turned out insufficient -- because
no code was ever executed this session (the shell/code-execution tool
failed on every command, including trivial ones with no dependency on this
task at all). See `NIGHT_BLOCKED.md` and `NIGHT_SUMMARY.md` for the full
diagnostic trail. What exists is the complete pipeline code and a
synthetic test suite with hand-computed expected results; none of it has
been run end-to-end (or at all) against real data. Nodes 1, 4, 5 are all,
equally, "not yet attempted" -- not "attempted and found lacking."

Read this file for what the pipeline *would* report once it's actually
run, and for the schema/design decisions made along the way.

## What this is

A soil-drydown calibration pipeline, evaluated as its own independent
candidate approach alongside `ml/option_one/` (FAO-56 bucket model) and
`ml/option_two/` (gradient-boosting forecast, on its own unmerged branch).
No neural network, no learned weather-to-curve mapping -- weather is a
direct input; what's fitted is a handful of physically-meaningful numbers
per node (`wet_ref`, `dry_ref`, `Kc`, `p`, a mm-to-raw-counts scale) via
`scipy.optimize.differential_evolution`. Each of nodes 1, 4, 5 is fit
completely independently -- no pooling, no shared parameters.

## Directory deviation (deliberate)

The spec this pipeline is drawn from describes a structure living
directly under `ml/` (`ml/data/`, `ml/model/`, `ml/events/`, etc). That's
**not** what's here, on purpose: `ml/data/` and `ml/models/` already exist
in this repo as top-level, DVC-tracked, **gitignored** directories (see
`ml/.gitignore`: `data/`, `models/`). Writing `ml/data/loaders.py` there
would silently vanish from git the moment it was added. Everything is
instead nested under `ml/option_three/`, mirroring how `ml/option_one/`
and `ml/option_two/` are each self-contained:

```
ml/option_three/
  configs/site.py               site constants, node scope, credential loading
  configs/cleaning_thresholds.py step-1 thresholds (config, not hardcoded)
  configs/window_thresholds.py   step-2 thresholds
  configs/nodes/node_{id}.json   fitted values per node (once calibrated)
  data/loaders.py                Supabase + Open-Meteo, disk-cached (gitignored cache dir)
  data/clean.py                  artifact detection, temperature corroboration
  events/windows.py              rain-stop detection, window extraction
  weather/subdaily.py            ET0 disaggregation
  model/drydown.py               the water balance, raw units, uneven timesteps
  model/calibrate.py             joint multi-window fit, one node at a time
  eval/validate.py               equifinality, hold-out, persistence, stage check
  reports/                       per-node reports + plots (empty tonight -- see STATUS.md)
  tests/                         synthetic leakage tests for cleaning + windows
  run_pipeline.py                orchestrates all of the above
```

## Scope -- firm

Nodes 1, 4, 5 only. Each fit fully independently (no pooling, no shared
parameters, no cross-node averaging). Raw ADC counts throughout, never the
0-100% mapping. Every reading at native ~20-minute cadence -- no daily
means, no resampling. Fits the drying period only (window start after
rain stops and the sensor turns; window end at the next rain with a
visible sensor response, or end of record).

## Schema findings

**Not independently verified against live data this session** (no
execution available) -- documented here from reading (never importing)
`ml/option_one/data_supabase.py` and its README, plus `firmware/` for the
ADC resolution:

- `readings(id, node_id, raw, recorded_at, received_at, rssi, snr,
  temperature)`, `sensor_calibration(node_id, air, water)`.
- Raw is a 12-bit ADC count (`analogReadResolution(12)` in
  `firmware/nodes/*/*.ino`), so `[0, 4095]` is the physical range-check
  bound.
- Known live-data issues per option_one's last audit (2026-09-03, not
  reverified tonight): ~16% duplicate packets (exact-payload match,
  dedup by earliest `received_at`), stray `node_id` values `0, 8, 9, 99`,
  `recorded_at` clock-sync issues with a `received_at` fallback. All three
  are reimplemented independently in `data/clean.py`/`data/loaders.py`
  (not imported from option_one).
- **Sign convention (which raw direction is "wetter") is undetermined**
  tonight -- it requires pulling a real rain event from Supabase, which
  requires code execution that wasn't available. `events/windows.py`'s
  `detect_sign_convention()` determines it empirically (majority vote
  across the largest rain events in the record) rather than assuming it;
  `model/drydown.py` doesn't even need the answer separately -- it derives
  the drying direction from the fitted `wet_ref`/`dry_ref` ordering, so
  it's correct either way once real data flows through.

## Cleaning (step 1)

`data/clean.py` implements, in order, each filtering before the next runs:
range check -> rate-of-change (gated on no rain in the preceding hour) ->
rolling-MAD local outlier (median/MAD excluding the point itself) ->
short-run detection (2-5 reading reverting shifts). Temperature
corroboration is computed for the rate-of-change and local-outlier flags
and reported separately (corroborated vs. not), per the spec -- it's not a
removal gate. Flagged points are removed, never interpolated. Thresholds
live in `configs/cleaning_thresholds.py`, none tuned against live data
yet (see file for reasoning behind each default). No cleaning report or
plot exists in `reports/` because no readings have ever been fetched --
see `reports/STATUS.md`.

## Drying windows (step 2)

`events/windows.py`: window start is the wettest point after rain stops,
confirmed by several subsequent readings continuing to dry (not a fixed
delay); window end is the next rain event with a raw-count response above
a configurable threshold, or end of record. Rain that doesn't produce a
visible response is recorded (`no_response`) but doesn't end a window.
Windows under 5 days are discarded. **Window counts per node: none yet --
zero data pulled.** A node with fewer than 3 usable windows can't be
calibrated (`model/calibrate.calibrate_node` raises rather than silently
producing a fit); that's a legitimate, plainly-reported finding per the
spec, not something to work around -- it just hasn't been reached for any
node tonight.

## Sub-daily weather (step 3)

`weather/subdaily.py` requests Open-Meteo's hourly
`et0_fao_evapotranspiration` directly when available (Open-Meteo computes
this via Penman-Monteith from its own hourly fields -- requesting it
directly is that method, without reimplementing the equation), falling
back to disaggregating daily ET0 across daylight hours via a
solar-elevation sine shape if the hourly column is missing/NaN. Which
method actually ran for a given fetch is reported alongside the result.
Neither path has been exercised against a real API response yet.

## The model (step 4)

`model/drydown.py`: single-store water balance in raw sensor units,
`loss = Ks(level) * Kc * ET0(interval)`, `Ks` kinked at depletion `p *
span` (`span = |dry_ref - wet_ref|`), integrated over the real elapsed
time between readings (partial-hour ET0 prorated from the hourly series).
`model/calibrate.py` fits `wet_ref, dry_ref, Kc, p, scale_mm_to_raw`
jointly across all of a node's windows via `differential_evolution`
(global search, since the `Ks` kink breaks gradient methods), each window
simulated from its own observed starting value, scored by KGE on the
concatenated full-resolution series. Strictly one node at a time.

## Validation (step 5)

`eval/validate.py`: equifinality (refit from >=12 seeds, mean/std/CV per
parameter -- CV > 0.2 reported explicitly as "not constrained by the
data"), hold-out (leave one window out, simulate it forward, report
error), persistence benchmark (reading-stays-put baseline at 3/7/14 days),
and a stage check (observed loss rate / ET0 over time per window --
flat throughout means `p` is unidentifiable from that window). None of
these have been run against real fits yet, so **no CV values, no
persistence comparison, and no hold-out error exist tonight.**

## Tests

`tests/test_drydown.py`, `tests/test_clean.py`, `tests/test_windows.py`
exercise the Ks kink, uneven-timestep ET0 integration, every cleaning
rule (individually and combined against a synthetic series with several
known injected artifacts), rain-event merging, empirical sign-convention
detection, and window-boundary detection against a hand-designed raw
series with known rain events and hand-computed expected window
boundaries. All were written and hand-traced against their inputs for
correctness; **none have been run by an actual test runner** (no `pytest`
execution was possible this session). Run `pytest ml/option_three/tests/`
before trusting them.

## Running it for real

```
pip install -r ml/option_three/requirements.txt
cp ml/option_three/.env.example ml/option_three/.env   # fill in real values
pytest ml/option_three/tests/
python -m ml.option_three.run_pipeline
```
