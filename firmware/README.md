# firmware

The code that runs on the ESP32 boards (see `hardware/circuit/` for the board they run on): the
field sensor nodes and the base-station hub that collects their LoRa transmissions. Built as
plain **Arduino IDE sketches** — each sketch lives in its own folder named identically to its
`.ino` file, which is what the Arduino toolchain requires to open/compile it.

- **`nodes/`** — the firmware flashed onto field sensor nodes. There are two configurations,
  depending on whether the physical board has a DS3231 RTC module fitted:
  - **`node_with_rtc/`** — has a DS3231 RTC, so it keeps accurate time on its own (backed by a
    coin cell) and wakes on a precise clock-aligned schedule.
  - **`node_no_rtc/`** — no RTC module. It times itself off the ESP32's internal (less accurate)
    clock and gets periodically corrected by a `TIME:` message from the hub.

  Both send readings over LoRa and log locally to flash (LittleFS) so a node can resend a backlog
  if it misses a transmission window. `NODE_ID` is a `#define` near the top of each sketch — set
  it uniquely before flashing each physical node.

- **`hub/`** — the base-station firmware: listens on LoRa, receives node packets, and replies
  during each node's listen window with `TIME:` / `GETDATA:` / `CFG:` commands. This is the
  counterpart nodes expect on the other end of the radio link.

- **`test/`** — standalone diagnostic/bench sketches, each named for what it verifies. Not part of
  the deployed system; flash these individually when debugging a specific piece:
  - `test_lora_rx_basic/` — bare-minimum LoRa receive, to check a board can hear packets at all.
  - `test_lora_field_range/` — walk-around field test: prints RSSI/SNR per packet and warns on
    signal loss, for checking real-world LoRa range/placement.
  - `test_supabase_insert_debug/` — WiFi-only (no LoRa), exercises the hub-to-Supabase HTTP insert
    path directly (plain insert / upsert / read-back) to isolate database-side issues.
  - `test_supabase_post/` — WiFi-only, posts synthetic fake readings to Supabase on a timer, for
    testing the ingestion path without needing real sensor hardware.
  - `test_node_with_rtc_v1_legacy/` / `test_hub_v1_legacy/` — an earlier node/hub pair, kept as
    reference. **Not compatible** with the current protocol: this node does on-device moisture
    calibration and sends a different message format, and this hub only listens/prints — it
    doesn't reply, so it won't work with the current `node_with_rtc` / `node_no_rtc` sketches.

- **`libraries/`** — third-party Arduino libraries used to build, vendored locally for
  convenience. **Not committed to git** (see `firmware/.gitignore`) — install these yourself via
  the Arduino Library Manager, pinned to the versions below:
  - LoRa (Sandeep Mistry) `0.8.0`
  - RTClib (Adafruit) `2.1.4`
  - Adafruit BusIO `1.17.4`
  - ArduinoJson `7.4.3`

The one thing firmware must never get out of sync with is `contracts/telemetry.md` — whatever
byte/field layout nodes and hub agree on between themselves must also match what `backend/`
expects once this moves off the current CSV-ish text protocol and onto the packed-byte contract.

**Heads up:** a couple of the `test/` sketches (`test_supabase_insert_debug`,
`test_supabase_post`) currently have a WiFi password and a Supabase API key hardcoded in plain
text. Fine for a bench test on a private network, but worth pulling into a gitignored config
before this repo goes anywhere less trusted.
