# DryAhead

Solo-built drought-monitoring sensor platform. 4 LoRa nodes live in the
field, reporting every 20 minutes.

## Repo map
- `contracts/` — `telemetry.md`, the LoRa packet byte layout. Backbone of
  the whole system.
- `firmware/` — ESP32 nodes (SX127x LoRa, DS3231 RTC). **Live-deployed.**
- `backend/` — FastAPI + Supabase/Postgres.
- `frontend/` — React + Vite, plain JS/JSX (not TS, despite the README).
  Deployed to Vercel from this subdirectory.
- `ml/` — drought-prediction model research. See `ml/CLAUDE.md`.
- `hardware/` — KiCad sources + fab outputs (not yet populated).

## Rules that must never be broken
1. **Contracts-first.** Any change to `contracts/telemetry.md`'s packet
   layout must update the firmware encoder, backend decoder, and the golden
   fixture together, in one change, bumping `packet_version`. Never
   reorder/resize an existing version's fields.
2. **`firmware/` is live on 4 field nodes.** Never edit firmware source
   without the user's explicit go-ahead — a bad deploy is expensive to fix
   in the field. Sleep-current budget is 11–12µA, non-negotiable.
3. **Never hand-edit anything in `hardware/`** — source or generated. Ask
   first.
4. **Never commit secrets.** Reference credentials as `${ENV_VAR}`, never
   literal values.

## Current state (2026-09) — verify before trusting
Several things referenced elsewhere in the repo are aspirational, not real
yet: the packed-byte telemetry contract (firmware still sends CSV-ish text),
firmware's CLI build (no `platformio.ini` exists), and CI (all 4 GitHub
Actions workflows are placeholders). Don't assume a command works because a
`justfile`/CI recipe references it — verify against the actual config first.
Per-package `CLAUDE.md` files have the specifics. See `.claude/SUGGESTIONS.md`
for proposed fixes to these gaps, not yet applied.
