# firmware

The code that runs on the ESP32 sensor node (see `hardware/circuit/` for the board it runs on).
Built with PlatformIO using the Arduino framework.

The firmware's job: read the soil moisture sensor, read the current time from the DS3231 RTC,
pack a reading into the byte layout defined in `contracts/telemetry.md`, and send it over LoRa
(SX127x) to a gateway.

- **`platformio.ini`** — board/framework config and library dependencies.
- **`src/main.cpp`** — the entry point (`setup()` / `loop()`).
- **`lib/`** — any local/private libraries specific to this project (PlatformIO convention).
- **`test/`** — PlatformIO unit tests.

The one thing firmware must never get out of sync with is `contracts/telemetry.md` — the packet
this code builds is parsed byte-for-byte by `backend/`.

To build: `just fw-build` (once PlatformIO is installed).
