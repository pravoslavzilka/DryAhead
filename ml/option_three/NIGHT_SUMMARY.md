# Night summary -- option_three (soil-drydown calibration)

**Supersedes an earlier version of this file.** The pipeline was originally
written blind: the agent's shell/code-execution tool failed on every
invocation that session (see git history / `overNightClaude` logs for the
original run), so none of steps 1-5 had ever actually been executed, and
the original `NIGHT_BLOCKED.md` documented that. This file replaces that
account after the code was actually run against live data, real bugs were
found and fixed, and a first real calibration succeeded. `NIGHT_BLOCKED.md`
has been removed since the blocker it described no longer applies.

## NIGHT_RULES/Supabase conflict, resolved

A follow-up unattended run on `night/drydown-calibration-run` correctly
stopped and refused to invoke `run_pipeline.main()`, flagging a real
conflict: `NIGHT_RULES.md` says, verbatim, "Never connect to Supabase or
any production database, read or write," with no read-only carve-out,
while this task requires exactly that (read-only anon-key access, same as
`ml/option_two/`'s already-established, already-approved pattern). That
was the right call for an unattended agent to make rather than silently
picking a side. Resolved here, in an attended session, by the person who
wrote both the original task spec (which explicitly specifies Supabase
read access) and `NIGHT_RULES.md`: the blanket rule is meant to prevent an
unattended agent from touching production state, not to block a read-only
`select`-only fetch that a prior, explicitly-scoped task already
authorized. That same run also reported the shell/PowerShell tool
alternating between spurious approval failures and bare `Exit code 66` on
trivial commands (`git status`, `echo hello`) -- independent of the rule
conflict, and consistent with similar shell-reliability problems reported
by the original option_three build and by a separate same-night IPP task.
Worth investigating as an environment issue if it recurs.

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

**All three nodes' main joint fits were run to completion**
(`differential_evolution`, one seed each):

| Node | Windows | KGE | Notes |
|---|---|---|---|
| 1 | 3 (8.0, 28.4, 8.2 d) | **0.977** | no parameter at a bound |
| 4 | 3 (20.7, 11.6, 15.3 d) | **0.927** | no parameter at a bound |
| 5 | 4 (11.7, 20.7, 13.1, 15.3 d) | **0.759** | **Kc, p, scale_mm_to_raw all at/near their upper bounds** -- see `reports/node_5.md`, this is flagged as a real problem, not accepted as a good fit |

Full parameter values and persistence-benchmark tables per node are in
`reports/node_{1,4,5}.md` and `configs/nodes/node_{1,4,5}.json`.
`reports/run_summary.json` rolls all three up.

**Not done, and why -- a platform constraint, not a scope choice:**
Equifinality (12-seed refit) and hold-out validation were planned to run
via a `night.sh`-launched unattended agent with an extended (280-minute)
timeout, since a full per-node validation is ~14 DE fits at ~6 minutes
each (~80-90 min/node, ~4h for all three) -- clearly a job for an
unattended run, not interactive back-and-forth. That attempt correctly
refused for an independent, valid reason (see next section). Handling it
interactively instead, every background-launched process doing sustained
CPU work in this session -- whether launched via `night.sh` or directly --
was killed by the environment well before a multi-fit job could finish,
consistently within several minutes, regardless of the declared timeout.
Only *foreground* tool calls that completed inside their own declared
timeout window survived reliably. That ceiling (proven safe up to ~590s)
is enough for exactly one main fit per call, which is how nodes 1/4/5's
main fits above were actually produced -- one at a time, foreground,
node 5 needed a loosened `tol` (5e-5 vs. the 1e-6 default) to converge
inside that window at all given its larger point count. Stacking 14 such
fits per node reliably, unattended, was not achievable in this session.
**If you have a way to run a long CPU-bound background job on this
machine/account that survives more than a few minutes, that's the
missing piece** -- the code itself doesn't need to change, just needs to
actually run `validate.equifinality(window_data, n_seeds=12)` and
`validate.holdout_validate(...)` per node, which `run_pipeline.main()`
(now resumable, commits per node) already does correctly.

## What I'm unsure about

- **Node 5's fit is likely not trustworthy as-is** -- three of five
  parameters pressed against their bounds, and its KGE (0.759) is well
  below nodes 1/4. Either the bounds (`Kc` in [0.1, 1.5],
  `scale_mm_to_raw` in [0.1, 300.0], both unvalidated against live data
  per the original task's own admission) are too tight for node 5's
  actual dynamics, or its 4 windows don't jointly pin these parameters
  down well. Needs a re-fit with widened bounds plus the equifinality
  check before trusting these numbers.
- Nodes 1/4's fits look good (high KGE, no bound-pressing) but are still
  single-seed point estimates -- without equifinality's CV per parameter,
  there's no way yet to say which of their parameters are actually
  constrained by the data versus coincidentally landing somewhere
  reasonable-looking.
- The `scale_mm_to_raw` bound (0.1-300.0) is unvalidated against live data;
  nodes 1/4 landed well inside it (21.2, 30.0) but node 5 landed at 291.7,
  right at the edge -- see above.
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


## Addendum -- node 4 equifinality run (this session)

Ran node 4's deferred equifinality check (12 seeds, foreground, one DE fit
per Bash call, ~270-410s each -- the same "one fit per foreground call"
pattern this file already documents as the only reliable way to run
sustained CPU work here). Full detail in `reports/node_4.md`; headline:

- KGE is essentially identical across all 12 seeds (mean 0.9272, std
  5.3e-10) -- the fit itself is robust.
- **Kc (CV 0.580) and scale_mm_to_raw (CV 0.683) are not constrained by
  node 4's 3 windows** -- many different values fit equally well. `p`
  (CV 0.201) is right at this pipeline's own 0.2 unconstrained threshold.
  Only wet_ref/dry_ref (CV 0.101/0.168) are well pinned down.
- Practical effect: node 4's single-seed main fit (Kc=0.144,
  scale_mm_to_raw=29.99) is one of many equally-valid parameter
  combinations, not "the" calibration. High KGE does not mean these
  physical parameters are individually trustworthy.

**New bug found, not yet fixed:** hold-out validation
(`eval/validate.holdout_validate`) trains on all windows except one held
out. Node 4 (and node 1) have exactly 3 windows -- this pipeline's own
stated minimum to calibrate at all -- so holding one out leaves 2 windows,
which `calibrate_node` refuses outright (`need at least 3 usable
windows`). This is a structural conflict, not an edge case: **no node
with exactly 3 windows can ever be hold-out validated as this code is
currently written.** Node 5 (4 windows) is unaffected. **User's call: loosen it.** `calibrate_node` gained a `min_windows`
parameter (default 3, unchanged for real calibration); `holdout_validate`
now passes `min_windows=2` for its own internal training fit only. Ran
node 4's hold-out with the fix: held out the 20.7-day window, trained on
the 11.6- and 15.3-day windows. Result: **held-out KGE = -0.287, RMSE =
140.9 raw** -- worse than node 4's own 14-day persistence baseline (131.5
raw). The fit does not generalize to an unseen window. Combined with the
equifinality result above, **node 4 is not recommended for drydown
prediction as currently calibrated** -- not because of a code bug, but
because the data doesn't constrain this model well enough yet. Node 1
still needs the same treatment (equifinality + hold-out) before any
prediction call can be made on it either; only node 4 was actually run
this session.
