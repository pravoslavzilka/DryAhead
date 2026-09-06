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

No parameter is pressed against a bound. Same caveat as node 1:
single-seed point estimate, equifinality/hold-out not run yet.
