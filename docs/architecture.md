# Architecture overview

## Data flow

```
[soil sensor] -> [ESP32 node, firmware/] --LoRa--> [gateway] -> [backend/] -> [Postgres]
                                                                       |
                                                                       v
                                                                  [ml/ model]
                                                                       |
                                                                       v
                                                                 [frontend/]
```

1. A field sensor node (`hardware/`, running `firmware/`) reads soil moisture, reads the current
   time from an onboard RTC, and packs a reading into the byte layout defined in
   `contracts/telemetry.md`.
2. The reading is sent over LoRa to a gateway, which forwards it to the `backend/` ingestion
   endpoint.
3. `backend/` parses the packet (per `contracts/telemetry.md`), stores it in Postgres, and later
   feeds historical readings to the model trained in `ml/`.
4. The model produces a forecast-primary drought prediction (see `docs/model-design/`), which
   `backend/` serves to `frontend/` for display.

## Why `contracts/` sits outside every domain folder

Firmware and backend are built, versioned, and (likely) deployed independently, but they must
agree byte-for-byte on the LoRa packet layout. Putting that definition in its own top-level folder
signals that it's not owned by either side — it's a shared interface both sides consume.

## Repository layout decision

See `docs/adr/0001-record-architecture-decisions.md` for why this project is a single monorepo
rather than six separate repositories.
