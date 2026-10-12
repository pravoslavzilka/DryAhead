# ml

Training code and experiments for the drought-prediction model. This is the *how*; the
scientific *what and why* lives in `docs/model-design/`.

- **`src/drought_ml/`** — the installable Python package: data loading, feature engineering,
  model training/inference code.
- **`notebooks/`** — exploratory notebooks.
- **`data/`** and **`models/`** — raw/processed datasets and trained model weights. These are
  **not committed to git** (see `ml/.gitignore`) — they're tracked with **DVC** instead, since
  they're large and change independently of code. Run `dvc init` (not done by this scaffold) and
  `dvc pull` once DVC remotes are configured.

The model consumes the readings the hub writes to Supabase (which originated from
`firmware/` over LoRa), read-only. The intended path is for `backend/` to serve the forecast to
`frontend/`, but for now the fitted parameters are exported as JSON and the dashboard runs the
model in the browser.

## Approaches

Different candidate approaches live in their own top-level folders here, evaluated on their own
merits before anything is picked as the platform's model:

- **`option_one/`** -- physically-based soil-water models calibrated per node against real
  sensor readings with differential evolution. No ML. Two generations:
  - **Combined FAO-56 bucket model** (`run_pipeline.py`) -- rain, drainage and ET in one
    bucket. Still loses to persistence; kept as a baseline.
  - **Split drying + wetting models** (`drydown.py` / `run_drydown.py`, `wetting.py` /
    `run_wetting.py`) -- **the working model**, nodes 1, 4, 5 on raw counts, local station
    weather. Held-out 7-day RMSE 8-10 counts vs 15-59 for persistence. Exported to the
    dashboard by `export_frontend_model.py` (`frontend/src/data/droughtModel.json`) and to
    the presentation page by `export_presentation_snapshot.py`. Fitted on 2026-07-01..09-25
    (summer only).

  See `option_one/README.md` for methodology and full results.
