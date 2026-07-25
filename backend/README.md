# backend

A FastAPI service that ingests sensor readings, stores them in Postgres, and serves them (plus
drought predictions) to `frontend/`.

- **`src/app/main.py`** — the FastAPI app, currently just a `/health` route. Ingestion endpoints
  (parsing packets per `contracts/telemetry.md`) and prediction-serving endpoints belong here.
- **`alembic.ini`** + **`migrations/`** — the database schema is **owned by the backend**: every
  schema change is a migration committed here, generated with Alembic.

This is the one service that talks to everything else: it receives data that originated in
`firmware/` (via a LoRa gateway), stores it in Postgres, calls into a trained model from `ml/`,
and is the API `frontend/` calls.

Run locally with `just backend` (needs a Postgres instance running and reachable — no containerized
setup yet, so start Postgres yourself for now).
