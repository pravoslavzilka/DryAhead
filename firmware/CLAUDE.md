# firmware/

**Live-deployed on 4 field nodes.** Never edit source here without the
user's explicit go-ahead — a bad flash is expensive to fix in the field.

## Non-negotiable
- Deep-sleep current budget: **11–12µA**. Any change touching peripheral
  power must preserve this.
- GPIO2 (`PERIPH_POWER`) gates all peripheral power (LoRa, moisture sensor,
  DS3231). Nothing draws current without going through it.
- Before sleep, I2C SDA/SCL and the RTC SQW pin are explicitly driven LOW in
  addition to cutting GPIO2 — the "12µA I2C-low fix," prevents the DS3231
  back-powering through I2C pull-ups.
- Sleep duration is computed from the RTC **before** power is cut (fixes a
  prior "240s bug": reading the RTC after power-down returned 0:0:0).
- `node_with_rtc` uses the DS3231 as its time source; `node_no_rtc` uses the
  ESP32's internal RTC, corrected by hub `TIME:` messages — not interchangeable.

## State, not aspiration
- Build system is **plain Arduino IDE sketches** — there is no
  `platformio.ini`. The `justfile`'s `fw-build` and `.github/workflows/
  firmware.yml` both call `pio run`, which currently fails.
- Wire format today is CSV-ish text (`node_id,raw,temperature,epoch,
  L:<0|1>`), **not** the packed-byte layout in `contracts/telemetry.md`.
  Don't assume the contract doc describes what's on the air right now.
- `test/test_supabase_insert_debug` and `test/test_supabase_post` have
  hardcoded WiFi/Supabase credentials committed in plaintext — known issue,
  fix pending user approval (see `.claude/SUGGESTIONS.md`). Don't copy that
  pattern into new code.
