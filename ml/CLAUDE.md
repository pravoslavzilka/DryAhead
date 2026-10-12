# ml/

Drought-prediction model research. **Do not touch Supabase directly** —
`option_one/`'s scripts read from it, nothing here should write to it.

## State, not aspiration
- `ml/option_one/` is a real, working, already-run pipeline (FAO-56
  root-zone bucket model, calibrated via `scipy.optimize
  .differential_evolution`, KGE-scored, forecasts via Open-Meteo
  ensembles) — not "designed, not yet built." It has already been run
  once against live Supabase data for 5 real nodes.
- `ml/option_one/` is committed (since `240c610`/`9873229`). Its working
  model is the split drying + wetting pair (`drydown.py`, `wetting.py`),
  exported to the dashboard via `export_frontend_model.py`; the combined
  `run_pipeline.py` bucket model is a baseline that still loses to
  persistence.
- `ml/src/drought_ml/` is the installable package and is still an empty
  stub — `option_one/` has not been integrated into it.
- No test framework, no lint/format config anywhere in this package.
- `ml/notebooks/`, `ml/data/`, `ml/models/` are empty scaffolding (only
  `.gitkeep`) — the plan is to track data/models with DVC, not yet
  initialized.
