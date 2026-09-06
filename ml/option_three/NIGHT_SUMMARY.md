# Night summary -- option_three (soil-drydown calibration)

**Supersedes an earlier version of this file.** The pipeline was originally
written blind: the agent's shell/code-execution tool failed on every
invocation that session (see git history / `overNightClaude` logs for the
original run), so none of steps 1-5 had ever actually been executed, and
the original `NIGHT_BLOCKED.md` documented that. This file replaces that
account after the code was actually run against live data, real bugs were
found and fixed, and a first real calibration succeeded. `NIGHT_BLOCKED.md`
has been removed since the blocker it described no longer applies.

## Directory-naming deviation (as instructed)

The spec this task is drawn from describes a structure living directly
under `ml/` (`ml/data/`, `ml/model/`, etc). That's not what's here: `ml/data/`
and `ml/models/` already exist as top-level, DVC-tracked, **gitignored**
directories in this repo (`ml/.gitignore`: `data/`, `models/`). Writing
`ml/data/loaders.py` there would silently vanish from git. Everything is
nested under `ml/option_three/` instead, mirroring `option_one/` and
`option_two/`.

## Real bugs found and fixed once the code actually ran

1. **Timestamp resolution was silently wrong by ~1000x** (`data/clean.py`,
   `resolve_timestamp`). The original code converted `received_at` to
   epoch seconds via `pd.to_datetime(...).astype("int64") // 10**9`,
   assuming nanosecond-resolution datetime64 storage. On this pandas
   version the actual resolution came back as microseconds, so every
   resolved timestamp collapsed to a few minutes after the Unix epoch
   (verified: all of node 1's ~6000 readings landed between
   1970-01-21 15:12 and 16:51). Fixed by doing the whole comparison in
   datetime-space (`pd.Timestamp`/`Timedelta`) instead of round-tripping
   through int64 epoch math, which is resolution-independent.
2. **`data/clean.py`'s `plot_cleaning` crashed with a pandas
   `AssertionError`** on real data: it received the caller's
   non-reset-index DataFrame while `flags` (from `clean_node`) were
   computed against a reset-index copy, so `df.loc[~any_flagged, "ts"]`
   indexed against mismatched labels. Fixed by resetting the index at the
   top of `plot_cleaning`, matching `clean_node`'s own convention.
3. **`events/windows.detect_sign_convention` failed outright on a real
   field node.** It only considered the 5 rain events with the largest
   site-wide total rainfall, but node 1 has real multi-week reporting
   gaps, and none of the 5 globally-biggest events happened to overlap
   its uptime. Fixed to rank by magnitude only among events the node
   actually has before/after readings for.
4. **Performance: a single objective evaluation took ~1.2s**, because
   `model/drydown.simulate_window` recomputed the (parameter-independent)
   ET0 integration from scratch, via per-step pandas calls, on every
   single call -- including every one of the tens of thousands of calls
   `differential_evolution` makes per fit. At that rate a single
   `calibrate_node` call was on the order of *hours*, not minutes, making
   the 12-seed equifinality check and hold-out validation completely
   infeasible. Fixed by adding `model/drydown.precompute_et0_intervals`,
   which computes the ET0-per-interval array once per window (it never
   changes during optimization), and changing `simulate_window` to accept
   that precomputed array instead of re-deriving it. This dropped a single
   objective evaluation to ~21ms (**~58x**), and a real 500-generation,
   3-window `calibrate_node` fit for node 1 to **363.8s (~6.1 min)**.
   `tests/test_drydown.py` updated to match the new `simulate_window`
   signature.

None of these were caught by the synthetic test suite, since the tests use
small hand-built series (a handful of points, one node's worth of clean
data) that don't exercise real multi-thousand-point series, real reporting
gaps, or realistic call volume. `tests/` still all pass (16/16) after every
fix.

## Real validation status (as of this commit)

Fetched live Supabase + Open-Meteo data for nodes 1/4/5 and ran cleaning +
window detection for real:

- Node 1: 5971 raw readings, 126 removed (7 range, 68 rate-of-change, 37
  local-outlier, 14 short-run), 5845 clean. Sign convention: wetter = lower
  raw (capacitive-typical), 3/5 of the top overlapping rain events agreed.
  **3 usable windows** (8.0, 28.4, 8.2 days) -- exactly at the task's
  minimum.
- Node 4: 7408 raw, 34 removed, 7374 clean. Same sign convention (3/5).
  **3 usable windows** (20.7, 11.6, 15.3 days).
- Node 5: 6928 raw, 21 removed, 6907 clean. Same sign convention (3/5).
  **4 usable windows** (11.7, 20.7, 13.1, 15.3 days).

All three nodes clear the "need >= 3 windows" bar -- none of them are the
"can't be calibrated yet" case the task spec anticipated as a legitimate
outcome.

**Node 1's main joint fit was run to completion** (differential_evolution,
default settings, 3 windows, ~3290 points total): KGE = **0.977**,
`wet_ref=2400.9, dry_ref=2590.9, Kc=0.379, p=0.711, scale_mm_to_raw=21.19`.
This is one seed's point estimate only -- the equifinality check (12 seeds)
and hold-out validation have not run yet for any node.

**Not yet done, and why:** the full per-node validation (12-seed
equifinality + hold-out, on top of the main fit) is ~14 full DE fits per
node at ~6 minutes each once fully converged -- roughly 80-90 minutes per
node, ~4 hours for all three. That's genuinely a job for an unattended
`night.sh` run with its own timeout, not something to force through
interactively. This branch is being handed back to `night.sh` with an
extended timeout to let it actually finish; whatever it produces lands in
`configs/nodes/node_{id}.json` and `reports/node_{id}.md` per node, with
`reports/run_summary.json` as the machine-readable roll-up. If you're
reading this before that run finished, check whether those files exist
yet.

## What I'm unsure about

- Only node 1 has been fit even once; nodes 4 and 5's fits, and the
  equifinality/CV numbers for all three, don't exist yet as of this
  commit -- see "Not yet done" above.
- The `scale_mm_to_raw` bound (0.1-300.0) is unvalidated against live data;
  node 1's fit landed at 21.19, comfortably inside the bound, which is a
  mild positive signal but not a substitute for checking whether the other
  two nodes also land away from the bound edges.
- Whether Open-Meteo's hourly `et0_fao_evapotranspiration` was actually
  populated for these date ranges was confirmed live: `et0_method =
  open-meteo-hourly-penman-monteith` printed for node 1 (not the
  solar-geometry fallback), so the primary path worked as hoped.
- The stray-node-ID and duplicate-packet handling inherited (by
  independent reimplementation, not import) from `option_one`'s audit
  reproduced a very similar duplicate rate (10.0% here vs. ~16% previously
  documented) -- close enough to be consistent, not re-derived from first
  principles.
- `events/windows.find_windows`'s extremum-confirmation loop is exercised
  by `tests/test_windows.py` on a synthetic series and now also on all
  three real nodes without crashing or producing an obviously wrong window
  count, but its edge-case behavior on data patterns not represented in
  either the synthetic test or these three nodes is still unverified.
