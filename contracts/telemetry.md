# Telemetry contract: LoRa sensor packet

This file is the **authoritative** definition of the byte layout sent by a firmware node over
LoRa and parsed by the backend. If you change a field here, you must update both `firmware/` and
`backend/` in the same change. This file is the source of truth — code should follow it, not the
other way around.

LoRa airtime is limited and power budget matters, so the payload is **packed bytes**, not JSON or
any other self-describing format. Every field has a fixed offset and width. Multi-byte integers
are little-endian.

## Packet layout (v1)

| Offset | Field                | Type          | Size (bytes) | Notes |
|-------:|-----------------------|---------------|:---:|-------|
| 0      | `packet_version`      | `uint8`       | 1 | Bump when the layout below changes. Lets the backend reject/branch on unknown versions. |
| 1      | `node_id`              | `uint8`       | 1 | Identifies which sensor node sent this reading. 0–255 nodes. |
| 2      | `timestamp`            | `uint32`      | 4 | Unix epoch seconds, read from the DS3231 RTC at send time. |
| 6      | `soil_moisture_raw`     | `uint16`      | 2 | Raw capacitive ADC reading (0–4095 for a 12-bit ADC), uncalibrated. |
| 8      | `soil_moisture_pct`     | `uint8`       | 1 | Calibrated 0–100%. See "Where calibration happens" below. |
| 9      | `battery_mv`            | `uint16`      | 2 | Battery voltage in millivolts, e.g. 3700 = 3.70 V. |
| 11     | `temperature_c_x10`     | `int16`       | 2 | Optional. Temperature in °C × 10 (one decimal place), e.g. 215 = 21.5°C. Sensor not always present — see below. |

**Total packet size: 13 bytes.**

### Handling an absent temperature sensor

Not every node has a temperature sensor. If absent, firmware sends the sentinel value
`INT16_MIN` (`-32768`) for `temperature_c_x10`. The backend must treat that sentinel as "no
reading," not as a real temperature.

### Where calibration happens

Firmware sends both `soil_moisture_raw` (uncalibrated ADC counts) and `soil_moisture_pct`
(calibrated 0–100%). The plan is for firmware to do a simple linear calibration on-device using
per-node dry/wet reference points stored in flash, but the raw value is always included too so the
backend can re-calibrate retroactively (e.g. after discovering a bad calibration) without needing
new firmware.

## Versioning

`packet_version` is field 0 for a reason: it lets the backend dispatch on layout before parsing
the rest of the packet. Never reorder or resize existing fields for an existing version — bump
`packet_version` and add a new parser instead. Keep old parsers around as long as old firmware
might still be in the field.

## Why one file for both sides

Firmware (the producer) and backend (the consumer) must both read their byte offsets from this
file, and only this file. Two independent hand-written implementations of the same layout will
eventually drift — a field gets reordered on one side and not the other, and you get silent data
corruption that's hard to detect from the field. Once the layout stabilizes, consider generating
the firmware struct and backend parser from a single schema (defined here or extracted from here)
so drift becomes a compile error instead of a runtime bug.
