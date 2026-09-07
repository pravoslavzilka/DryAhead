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

The model consumes historical readings that `backend/` has ingested (which originated from
`firmware/` over LoRa, per `contracts/telemetry.md`), and produces the forecast that `backend/`
serves to `frontend/`.

## Approaches

Different candidate approaches live in their own top-level folders here, evaluated on their own
merits before anything is picked as the platform's model:

- **`option_one/`** -- a physically-based FAO-56 root-zone bucket model, calibrated per node
  against real sensor readings with differential evolution (KGE-scored). No ML. Already built
  and run against live Supabase data (see `option_one/README.md` for current results) --
  **intentionally left uncommitted (untracked in git)** for now, so don't assume it's missing
  if `git status` shows it that way; committing it is the user's call on their own timeline.
