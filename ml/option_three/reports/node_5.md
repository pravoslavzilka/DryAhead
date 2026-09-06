# Node 5 -- drydown calibration

**4 usable windows** (11.7, 20.7, 13.1, 15.3 days -- the last ending at
end-of-record), out of 10 detected -- the best-covered of the three nodes.
Sign convention: wetter = lower raw, 3/5 of overlapping top rain events
agreed.

**Persistence benchmark**, MAE (raw counts):

| Horizon | n windows | MAE (raw) |
|---|---|---|
| 3 days | 4 | 241.5 |
| 7 days | 4 | 243.5 |
| 14 days | 2 | 490.0 |

**Main fit** (single seed, `tol=5e-5` -- looser than the 1e-6 used for
nodes 1/4, needed to converge within the available compute window given
this node's larger total point count across 4 windows; see
`NIGHT_SUMMARY.md`): **KGE = 0.759** -- clearly worse than nodes 1/4.

| Param | Value | |
|---|---|---|
| wet_ref | 2169.2 | |
| dry_ref | 2599.3 | |
| Kc | **1.496** | pressed against upper bound (1.5) |
| p | 0.900 | at upper bound (0.9) |
| scale_mm_to_raw | **291.7** | pressed against upper bound (300.0) |

**Flagging this plainly, not burying it:** three of five parameters are at
or pressed right against their upper bounds. That is a real sign this
node's fit is not well-constrained by the current bounds/data -- either
the bounds (`Kc` in [0.1, 1.5], `scale_mm_to_raw` in [0.1, 300.0], both
unvalidated against live data per the original task's own admission) are
too tight for this node's actual dynamics, or this node's 4 windows don't
pin these parameters down well jointly. The lower KGE (0.759 vs. 0.98/0.93
for nodes 1/4) is consistent with a poorer fit rather than a fluke. Do not
trust this node's parameters as final without widening the bounds and
re-fitting, and without the equifinality check (not run) to see whether
these values are stable across seeds or an artifact of one run pressing
against the boundary.
