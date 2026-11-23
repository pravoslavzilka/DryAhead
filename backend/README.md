# backend

A FastAPI service, intended to own ingestion (parsing packets per `contracts/telemetry.md`),
the database schema, and prediction-serving for `frontend/`. **Not yet in the live data
path** — see below.

- **`src/app/main.py`** — currently a 9-line stub with only a `/health` route. No ingestion or
  prediction-serving code exists yet.
- **`alembic.ini`** + **`migrations/`** — Alembic is configured (schema changes are meant to be
  committed here as migrations), but `migrations/` is empty — no schema is tracked yet.

**Today, the hub writes straight to Supabase over its REST API** — this service isn't in that
path at all. The intended shape (hub → this backend → Postgres, with packet parsing and
validation against `contracts/telemetry.md`) hasn't been built. When it is, this becomes the
one service that talks to everything else: receiving data that originated in `firmware/`,
storing it, calling into a trained model from `ml/`, and serving `frontend/`.

Run locally with `just backend` (needs a Postgres instance running and reachable — no containerized
setup yet, so start Postgres yourself for now). No lock file exists yet (bare `pyproject.toml`,
hatchling backend), and there's no test/lint/format tooling configured in this package.

- **`reconciliation/`** — a standalone script (own `requirements.txt`, no shared code with the
  FastAPI app) that finds gaps in sensor readings and queues backfill instructions for the hub.
  Meant to run on a schedule (cron / systemd timer / serverless), independent of this service. See
  `reconciliation/README.md`.
