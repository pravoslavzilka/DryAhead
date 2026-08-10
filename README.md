# DryAhead

**Forecast-primary drought early warning — from a sensor in the soil to a prediction on the screen.**

DryAhead is an end-to-end platform that measures soil moisture in the field, transmits it over long-range radio, and combines it with weather forecasts to predict drought stress *before* it happens. The name says the goal: see the dry conditions **ahead** of time, while there's still time to act.

---

## Objective

Growers and land managers usually learn about drought stress once the damage is already visible. DryAhead aims to move that signal earlier by fusing two things:

1. **Ground truth** — real soil-moisture readings from cheap, rugged, battery-powered field nodes.
2. **The forecast** — weather predictions, corrected against the ground-truth readings through data assimilation.

The result is a *forecast-primary* drought prediction: not just "how dry is it now," but "how dry is it about to get, here, in this specific plot." The target users are viticulture, orchards, and forestry operations, with a second track aimed at institutional buyers such as parametric-insurance and risk modelling.

---

## Project status

Early stage. The hardware design and the modelling approach are defined; the codebase is being scaffolded now. Nothing here is production-ready yet.

| Area | Status | Notes |
|------|--------|-------|
| Sensor node (hardware design) | 🟡 Specified | Pinout defined (see below); prototype bring-up next |
| Enclosure | 🟡 Specified | Sealed KG DN160 pipe, antenna inside |
| Firmware | ⚪ Skeleton | Sleep/measure/transmit loop not yet written |
| Data contract | 🔴 To define first | `contracts/telemetry.md` — the priority before anything downstream |
| Backend + ingestion | ⚪ Skeleton | FastAPI app stub only |
| Database | 🟡 Chosen | PostgreSQL (TimescaleDB candidate for time-series) |
| ML model | 🟡 Approach defined | Forecast-primary + data assimilation; not yet trained |
| Frontend | ⚪ Skeleton | Map + dashboard, not started |
| Market validation | 🟡 In progress | Segments identified; Lean Canvas per buyer type in development |

Legend: 🔴 do first · 🟡 designed / in progress · ⚪ skeleton only

---

## How it works

A single soil-moisture reading travels through every part of the system. Each part must read it in exactly the same format — which is why the **data contract** is the backbone of the whole repo, not an afterthought.

```
[ soil moisture sensor ]   measures the reading
          │
          ▼
[ firmware (ESP32) ]       packs it into a compact LoRa message
          │  ~ LoRa (SX127x) ~
          ▼
[ backend + database ]     receives and stores the message
          │
          ▼
[ ML model ]               fuses it with the forecast → drought prediction
          │
          ▼
[ frontend ]               shows the result on a map / dashboard

        ▲
        └── contracts/telemetry.md defines the message format every stage reads
```

If the firmware and the backend ever disagree about that format — say one sends a raw ADC integer and the other expects a calibrated percentage — nothing crashes, but the data is silently wrong and the model trains on garbage. One authoritative spec prevents that.

---

## Repository structure

```
dryahead/
├── docs/            Written explanations and decisions (not code)
│   ├── model-design/    The scientific model: the *what & why* of the forecast
│   └── adr/             Architecture Decision Records — why we chose X over Y
├── contracts/       ⭐ The shared data format every part agrees on
├── hardware/        The physical device (design files, not code)
│   ├── circuit/         KiCad schematic + PCB
│   ├── enclosure/       CAD/STL for the pipe enclosure + antenna mount
│   └── bom.csv          Bill of materials (the parts list)
├── firmware/        C++ code that runs *on* the ESP32 chip
├── ml/              Python code that trains and runs the drought model
├── backend/         FastAPI server: ingests readings, owns the database
├── frontend/        The web app people actually look at
└── infra/           Deployment and local-dev setup (Docker, CI)
```

Each folder has its own README explaining, in plain language, what belongs there and what it talks to.

---

## The sensor node

A low-power ESP32 node that wakes on a schedule, takes a reading, transmits it over LoRa, and goes back to sleep — designed to run for a long time on battery in a sealed field enclosure.

**Core components**

- **MCU:** LaskaKit ESP32-DevKit
- **Radio:** LoRa, Semtech SX127x (long range, low power, no cellular/WiFi needed in the field)
- **Real-time clock:** DS3231, used to wake the board on a precise schedule
- **Soil sensor:** capacitive soil-moisture probe (no exposed electrodes to corrode)
- **Enclosure:** sealed KG DN160 pipe with the antenna housed inside

**Pin assignment (current design — confirm against the board before flashing)**

| Function | Pin | Notes |
|----------|-----|-------|
| DS3231 SDA (I²C) | GPIO21 | Real-time clock data |
| DS3231 SCL (I²C) | GPIO22 | Real-time clock clock |
| DS3231 SQW → wake | GPIO33 | Alarm interrupt wakes the ESP32 from deep sleep |
| Soil moisture (analog) | GPIO34 | ADC1 input (input-only pin) |
| Peripheral power gate | GPIO2 | Cuts power to sensor/peripherals between readings |
| LoRa SX127x | SPI (VSPI) | CS / RST / DIO0 — to be confirmed and documented |

The design intent is **deep sleep by default to prolong battery life**: for most of the day the ESP32 sits in deep sleep drawing almost no current. The RTC's alarm (SQW → GPIO33) wakes the MCU, the power gate (GPIO2) energises the sensor only for the brief measurement window, a reading is taken on GPIO34, packed per the data contract, sent over LoRa, and the node immediately returns to deep sleep. Because it's awake only for a few seconds per reading, a single battery charge can last many months in the field.

---

## The model

DryAhead's prediction is **forecast-primary**: the backbone of the estimate is the weather forecast, and the field readings are used to **correct and anchor** that forecast to real local conditions through data assimilation. This matters because a forecast alone doesn't know the state of *your* soil, and a sensor alone can't see the future. Combining them gives a per-location, forward-looking drought signal.

The scientific design (assumptions, assimilation method, evaluation) lives in `docs/model-design/`, kept separate from the training code in `ml/` — the *what & why* apart from the *how*.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Firmware | PlatformIO · ESP32 · Arduino framework |
| Radio | LoRa SX127x |
| Backend | Python 3.12 · FastAPI · SQLAlchemy · Alembic |
| Database | PostgreSQL (TimescaleDB candidate) |
| ML | Python 3.12 · DVC for data/model versioning |
| Frontend | React · Vite · TypeScript |
| Local dev | Docker Compose |
| CI | GitHub Actions (path-filtered per component) |
| Large files | git-lfs (hardware binaries) · DVC (datasets, weights) |

---

## Roadmap

1. **Define `contracts/telemetry.md`** — the LoRa payload byte-layout. Everything downstream depends on this.
2. **Firmware bring-up** — sleep → wake → measure → pack → transmit loop on real hardware.
3. **Backend ingestion** — receive LoRa messages, validate against the contract, store in Postgres.
4. **First data collection** — get real readings flowing into the database from a field node.
5. **Model v0** — forecast-primary baseline with simple assimilation, evaluated against collected data.
6. **Frontend** — map + dashboard showing live readings and the drought prediction.
7. **Concierge MVP** — deliver predictions to a first pilot user manually before automating the full pipeline.

---

## The name

**DryAhead** — a drought forecast is a warning that dry conditions lie *ahead*, and a good early-warning system keeps you a step *ahead* of them. Say it out loud and it also reads as "dry ahead": that's the whole product in two words.