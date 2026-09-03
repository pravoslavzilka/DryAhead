---
name: telemetry-contract
description: Mandatory ordered procedure for any change to the LoRa packet layout in contracts/telemetry.md - use whenever a task involves adding, removing, resizing, or reordering a telemetry field, or bumping packet_version. Also use when asked to explain how a packet-layout change should be sequenced.
---

# telemetry-contract

`contracts/telemetry.md` is the backbone of the whole system: firmware
encodes against it, backend decodes against it. A change made in only one
place is a live incident waiting to happen. Follow this order; don't skip
steps.

## Current state (read this first)
The packed-byte v1 layout documented in `contracts/telemetry.md` is **not
implemented yet** — firmware still sends CSV-ish text, backend has no
parser, and no golden fixture exists. See `.claude/SUGGESTIONS.md` item 1
for the proposed encoder/decoder/fixture work. Until that lands, steps
4-6 below describe what to do *once it exists*, not something already
wired up today.

## Procedure

1. **Classify the change.** Adding a new field at the end is additive and
   safe. Reordering, resizing, or removing an existing field is breaking.
2. **If breaking, bump `packet_version`.** Never mutate an existing
   version's byte layout — old firmware in the field may still send the
   old version. Add a new parser branch instead of replacing the old one.
3. **Update `contracts/telemetry.md`** — the field table and the
   versioning notes. This is the single source of truth; everything else
   below derives from it.
4. **Update the firmware encoder** to match the new layout (whichever
   node sketches build the packet).
5. **Update the backend decoder** to match, including a new
   `packet_version` branch if this is a breaking change.
6. **Update the golden fixture** (`contracts/fixtures/golden_packet_v1.json`
   or the equivalent for the new version) — known bytes, known decoded
   values — and confirm both the firmware-side and backend-side tests
   pass against it.
7. **Land it as one change.** Contract, firmware, backend, and fixture
   move together in a single PR/commit — never split across separate
   changes that could land out of order.
8. **Keep old-version parsers around** on the backend as long as any
   deployed node might still be sending an older `packet_version`.

## Reminders already enforced by tooling
- Touching `contracts/telemetry.md` triggers a hook reminder summarizing
  steps 4-6 (`.claude/hooks/contract_touch_reminder.py`).
- While the repo's source-edit guard is active (config-only pass, see
  `.claude/SETUP.md`), edits under `firmware/`, `backend/`, and
  `contracts/` are blocked outright — this procedure documents the order
  for when that guard is lifted and the work is actually authorized.
