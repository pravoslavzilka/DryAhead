# Suggestions — not applied

Written during the 2026-09 Claude Code configuration pass. Everything below
touches application source, build config, credentials, or repo/git state
outside `.claude/**` — per your instruction, none of it was implemented.
Review and greenlight items individually whenever you're ready; nothing
here expires.

---

## 1. Golden packet fixture (highest priority)

**What:** A fixed 13-byte fixture (known bytes ↔ known field values) per
`contracts/telemetry.md` v1, stored at
`contracts/fixtures/golden_packet_v1.json`. Firmware gets a small,
unit-testable `encode_telemetry_packet()` exercised by a new PlatformIO
native test target (no hardware needed). Backend gets
`decode_telemetry_packet()` + a pytest asserting the same fixture.

**Why:** `contracts/telemetry.md`'s packed-byte layout isn't implemented
anywhere today — firmware still sends CSV-ish text
(`node_id,raw,temperature,epoch,L:<0|1>`) and backend has no parser. A
golden fixture is the standard way to guarantee encoder and decoder agree,
and it's the natural first deliverable once this protocol migration is
authorized.

**How to apply:** Because no real node emits the packed format yet, "capture
a real fixture" can't be done literally right now. Hand-construct the first
fixture from known values, verify both sides against it, and only replace
it with a real-captured fixture once a **bench node** (not a field node) is
flashed with the new encoder — capture the actual over-the-air bytes from
the hub's debug log, then update firmware test, backend test, and fixture
file together (this is exactly what the `telemetry-contract` skill walks
through).

**Do not flash this to any of the 4 field nodes as part of enabling it** —
that's a separate, later `firmware-release` action with its own rollout
plan, not a side effect of adding a codec.

**Effort:** medium (new firmware module + native test env, new backend
module + pytest, fixture file, storage table doesn't exist yet either —
see item 6's backend note).

---

## 2. `platformio.ini` for firmware

**What:** A real PlatformIO project file, migrating firmware off pure
Arduino-IDE-sketch builds onto a CLI-buildable one (`pio run`).

**Why:** The root `justfile`'s `fw-build` recipe and
`.github/workflows/firmware.yml` both already call `pio run` — and both are
broken right now because no `platformio.ini` exists. Adding one fixes both
for free and is the prerequisite for a firmware `check.sh` and the golden
fixture's native test target (item 1).

**How to apply:** Define environments for `node_with_rtc`, `node_no_rtc`,
and `hub` (matching the existing `firmware/nodes/*` and `firmware/hub/`
sketch layout), pin the LoRa/RTClib/BusIO/ArduinoJson library versions
currently vendored manually under the gitignored `firmware/libraries/`, and
add a `native` test environment for codec unit tests that don't need
hardware.

**Effort:** low-medium. Mostly config; no application logic changes.

---

## 3. Credential hygiene item — kept out of git

Intentionally not detailed here: this repo is public, and an actionable
"here's exactly where the live secret is" writeup doesn't belong in git
history alongside it. See `.claude/SUGGESTIONS.local.md` (gitignored,
local-only) for the specifics and how to apply.

---

## 4. Remove the stale `fe` git remote

**What:** `git remote remove fe` — you confirmed this
(`github.com/pravoslavzilka/DryAhead-frontend`) is leftover and unused.

**Why:** Not touched this pass because it's a repo-state change outside
`.claude/**`.

**How to apply:** `git remote remove fe`, then `git remote -v` to confirm
only `origin` remains. Trivially reversible (`git remote add fe <url>`) if
it turns out to matter.

**Effort:** trivial.

---

## 5. Wire CI to real checks

**What:** `.github/workflows/{frontend,backend,ml,firmware}.yml` currently
all run placeholder steps (three literally print `"...placeholder"`;
firmware's `pio run` step would fail with no `platformio.ini`). Once each
package has a `check.sh` (item 6) and `platformio.ini` (item 2) exist,
replace the placeholder step in each workflow with a call to the matching
`check.sh`.

**Why:** Keeps CI and local verification as one source of truth instead of
two things that can silently drift apart.

**Effort:** low, once items 2 and 6 land — this is genuinely just deleting
the placeholder `echo`/`print` lines and calling the real script.

---

## 6. Per-package `check.sh` (proposed contents)

Not created this pass (would touch package directories / require tooling
not yet installed). Proposed contents, to wire into the existing
`justfile` as `check` / `check-<pkg>` recipes when you're ready:

| Package | Proposed `check.sh` |
|---|---|
| `firmware/` | `pio run` for the 3 build envs, + `pio test -e native` for the packet-codec unit test (needs item 1 + item 2 first) |
| `backend/` | `pytest`, scoped to the golden-fixture decoder test initially (needs item 1; `pytest` would be added as a narrow dev-dependency, not broad scaffolding — matches your earlier "build+lint only, beyond the golden fixture" call) |
| `frontend/` | `npm run build` (already verified working today, no blockers) |
| `ml/` | `python -c "import drought_ml"` — an honest smoke test given `ml/src/drought_ml/` is still an empty stub |
| `hardware/` | none — nothing to verify until real KiCad sources exist |

Note: `backend/`'s decoder test also implies a place to *store* decoded
telemetry, which doesn't exist yet either (Alembic is configured but
`migrations/` is empty) — the first real migration is naturally scoped
together with item 1, not before it.

---

## 7. `db-migration` and `firmware-release` skills

**What:** Two more `.claude/skills/` entries from the original proposal,
not built this pass.

**Why deferred:**
- `db-migration` — nothing to document a real Alembic write/apply/rollback
  procedure against until the first migration actually exists (tied to
  item 1/6).
- `firmware-release` — a version-bump/build/size-check/sleep-current-
  sanity/flash/tag checklist needs a working CLI build first (item 2).

**How to apply:** Build these once their prerequisites land — they're
cheap to add at that point and not useful before it.

---

## 8. Committing `ml/option_one/`

**What:** `ml/option_one/` (a real, working, already-run FAO-56
bucket-model pipeline — 1,385 lines, calibrated and forecast-tested against
live Supabase data) is currently untracked in git.

**Why not touched:** explicitly your call, on your own timeline — noted
in `ml/CLAUDE.md` as intentionally uncommitted so no future session
assumes otherwise or stages it by accident.

**How to apply:** whenever you're ready — `git add ml/option_one/` and
commit. No urgency from a tooling-config perspective; the directory works
fine uncommitted for now.
