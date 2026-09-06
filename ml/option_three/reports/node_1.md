# Node 1 -- drydown calibration

**3 usable windows** (8.0, 28.4, 8.2 days), out of 16 detected before the
>=5-day filter. Sign convention: wetter = lower raw (capacitive-typical),
3/5 of overlapping top rain events agreed.

**Persistence benchmark** ("reading stays where it is"), mean absolute
error in raw counts:

| Horizon | n windows | MAE (raw) |
|---|---|---|
| 3 days | 3 | 37.3 |
| 7 days | 3 | 35.7 |
| 14 days | 1 | 214.0 |

**Main fit** (single seed, `differential_evolution` default settings,
tol=1e-6): **KGE = 0.977**.

| Param | Value |
|---|---|
| wet_ref | 2400.9 |
| dry_ref | 2590.9 |
| Kc | 0.379 |
| p | 0.711 |
| scale_mm_to_raw | 21.19 |

None of the fitted parameters are pressed against a bound. This is a
single-seed point estimate -- **equifinality (12-seed refit) and hold-out
validation have not run for this node**; the CV per parameter that would
say whether each value is actually constrained by the data doesn't exist
yet. See `NIGHT_SUMMARY.md` for why (compute budget).
