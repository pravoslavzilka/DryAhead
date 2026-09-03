# backend/

FastAPI service, meant to own the schema via Alembic and parse telemetry
per `contracts/telemetry.md`. **Do not touch Supabase directly** (no CLI
migrations run against it, no manual data changes).

## State, not aspiration
- Package manager is a bare `pyproject.toml` (hatchling build backend) —
  **no lock file** exists.
- No ingestion/parsing code exists yet: `src/app/main.py` is a 9-line stub
  with only a `/health` route.
- Alembic is configured (`alembic.ini`, `script_location = migrations`) but
  `migrations/` is empty — no schema is tracked yet.
- No test framework, no lint/format config (no pytest, ruff, black, mypy
  anywhere in this package).
- Verified dev run (from the root `justfile`):
  `cd backend && uvicorn app.main:app --reload --app-dir src`

## Separate, unrelated tool
`backend/reconciliation/` is a standalone script with its own
`requirements.txt` — don't assume it shares dependencies or structure with
the FastAPI app.
