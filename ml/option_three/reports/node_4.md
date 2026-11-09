# Node 4 -- drydown calibration

**3 usable windows** (20.7, 11.6, 15.3 days -- the last ending at
end-of-record, not rain), out of 16 detected. Sign convention: wetter =
lower raw, 3/5 of overlapping top rain events agreed.

**Persistence benchmark**, MAE (raw counts):

| Horizon | n windows | MAE (raw) |
|---|---|---|
| 3 days | 3 | 73.0 |
| 7 days | 3 | 127.0 |
| 14 days | 2 | 131.5 |

**Main fit** (single seed, default settings, tol=1e-6): **KGE = 0.927**.

| Param | Value |
|---|---|
| wet_ref | 2013.9 |
| dry_ref | 2253.4 |
| Kc | 0.144 |
| p | 0.521 |
| scale_mm_to_raw | 29.99 |

No parameter is pressed against a bound.

**Equifinality (12 seeds, differential_evolution, seed=0..11):** KGE is
essentially identical across every seed (mean 0.9272, std 5.3e-10) -- the
optimizer reliably finds an equally-good fit every time. But the
parameters it finds to get there vary a lot:

| Param | Mean | Std | CV | Constrained? |
|---|---|---|---|---|
| wet_ref | 2217.5 | 223.6 | 0.101 | yes |
| dry_ref | 2660.5 | 447.1 | 0.168 | yes |
| Kc | 0.418 | 0.243 | **0.580** | **no** |
| p | 0.677 | 0.136 | 0.201 | borderline (at this pipeline's own 0.2 cutoff) |
| scale_mm_to_raw | 16.3 | 11.2 | **0.683** | **no** |

**Flagging this plainly:** the single-seed main fit above (Kc=0.144,
scale_mm_to_raw=29.99) is one of many equally-valid basins, not "the"
answer -- across seeds, Kc ranged as high as 0.80 and scale_mm_to_raw as
low as 5.4, all scoring the same KGE. The 3 windows this node has jointly
constrain wet_ref/dry_ref reasonably well, but do not identify the
crop-stress parameters (Kc, p, scale_mm_to_raw) individually. High KGE
here means "this model family reproduces the observed series," not "these
are this node's true Kc/p/scale values" -- don't quote a lone fitted value
for Kc, p, or scale_mm_to_raw from this run.

**Hold-out validation:** run after loosening `calibrate_node`'s
window floor specifically for hold-out's own training fit
(`min_windows=2`, user-approved -- see NIGHT_SUMMARY.md; the node has
exactly 3 windows, the task's own stated minimum to calibrate at all, so
training on windows-minus-one otherwise leaves 2, below the normal
3-window floor). Held out the 20.7-day window, trained on the 11.6- and
15.3-day windows:

| | Value |
|---|---|
| held-out KGE | **-0.287** |
| held-out RMSE (raw) | 140.9 |

**This fails outright.** Negative KGE, and the RMSE (140.9) is worse than
this node's own 14-day persistence baseline (131.5 raw, see above) -- the
calibrated model, refit on the other two windows, predicts the held-out
window worse than just assuming the reading doesn't move. Combined with
the equifinality result above, node 4's fit does not generalize and
should not be used for drydown prediction as-is. (Caveat: this hold-out
fit trained on only 2 windows, thinner than the normal 3-window floor, so
some of the failure may reflect that thinner training rather than pure
non-generalization -- but a fit that can't hold up on 2 training windows
is not evidence in favor of trusting the 3-window main fit either.)
