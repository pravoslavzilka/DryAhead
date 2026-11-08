# DryAhead

**A soil-moisture sensor network monitoring drought risk in the field — live since June 2026.**

DryAhead measures soil moisture in the field, carries it over long-range LoRa radio to a
cloud database, and shows it on a live dashboard. The eventual goal is to fuse those
readings with weather forecasts to predict drought stress *before* it happens — the name
says the goal: see the dry conditions **ahead** of time, while there's still time to act.
A first working forecast is live on the dashboard for nodes 1, 4 and 5: when each spot
reaches plant stress if no rain falls, plus a with-forecast-rain line — see
[The model](#the-model).

Live dashboard: **[dryahead.com](https://dryahead.com/)**

---

## Field deployment

Five nodes and a hub have been running unattended near Zaježová (Pliešovce, Slovakia)
since **2026-06-29**, across five points within a 500 m radius. As of **2026-10-12**
(105 days in), Supabase holds **42,003 readings** from the five nodes:

| Node | Status | Days with data | Delivered slots | Delivery rate |
|------|--------|---------------:|----------------:|--------------:|
| 1 | in operation | 106 | 6,121 / 7,595 | 80.6% |
| 2 | **rebuilt, in operation since 2026-10-11** — node 2's body with node 3's reprogrammed board (see below) | 12 | 469 / 7,595 | 6.2% |
| 3 | **retired** — last field reading 2026-09-10; water in the antenna chamber stopped transmission. Its board now runs node 2 | 46 | 2,598 / 7,595 | 34.2% |
| 4 | in operation | 106 | 6,624 / 7,595 | 87.2% |
| 5 | in operation — battery ran out 2026-10-05, replaced 10-11 | 101 | 6,196 / 7,595 | 81.6% |
| **Total** | | | **22,008 / 37,975** | **58.0%** |

A *slot* is one 20-minute reading interval; the denominator is every slot from the first
reading (2026-06-29) to 2026-10-12, the same for every node. Row counts run at about twice
the slot counts because nodes 1, 4 and 5 log two readings 8–13 s apart in most slots (a
double wake per cycle, still to be fixed in firmware) — analysis code dedupes per slot.

**Node history.**

- **Node 2 (original):** a bad solder joint from the build kept the ESP32 from entering deep
  sleep, so it drained its battery. It went silent on 2026-08-08, and the repair attempt
  permanently destroyed its ESP32 board.
- **Node 3:** poor sealing of the antenna chamber let water droplets in, and the
  contamination stopped it transmitting. Its last field reading was 2026-09-10. The board
  itself still worked.
- **Node 2 (rebuilt):** node 3's board, reprogrammed as node 2, was fitted into node 2's
  body. It has been reporting since 2026-10-11 17:33 UTC, so rows for node 2 before
  2026-08-08 come from the old board. Its timestamps look healthy so far: 1 of its first 153
  readings has epoch 0.
- **Node 5:** its battery ran out on 2026-10-05 (last reading 06:00 UTC). After a new
  battery it was back on 2026-10-11 at 17:39 UTC.

The nodes without a hardware fault (1, 4, 5) deliver 81–87%, so the network's ceiling is
set by enclosure/mechanical reliability, not the radio link or cloud stack — LoRa RSSI held
between −95 and −97 dBm with no observed distance dependence within 1 km.

**Manual recovery from a node's flash (node 3, 2026-10-11).** Before node 3's board was
reprogrammed as the new node 2, its full local log (10,075 readings, 06-29 → 10-11) was
pulled over USB with
`tools/node_log_dump/` and cleaned before upload: the 8–13 s double readings were merged
per slot and every slot already in Supabase was dropped, leaving **505 new readings**
(mostly 07-26 → 08-05 and 09-09/10) inserted as `is_backlog = true`. A further 4,889 readings
weren't uploaded because they have no usable timestamp: from late July the node's DS3231
stopped answering around midday (roughly 10:00–18:00 UTC) and was almost completely dead
from 08-06, so those readings carry epoch 0. See [`tools/`](#repository-structure).

The hub also recovers missed readings after connectivity outages via `GETDATA` requests
(see `backend/reconciliation/`). In the one outage tested against so far (59.6 h in
August), only 23% of the missed readings were recovered, because reconciliation ran later
than the nodes' 14-day local retention window — an operational lesson, not a design flaw,
and the reason `backend/reconciliation/` is meant to run on a recurring schedule shorter
than that window.

**Known limitation:** the soil sensors haven't been calibrated against a reference
(gravimetric) method, so readings are a raw relative signal — useful for tracking trends,
not yet a calibrated volumetric-moisture percentage.

---

## Project status

| Area | Status |
|------|--------|
| Sensor nodes + hub firmware | **Live-deployed** — 4 field nodes reporting every 20 min, deep-sleep current 11–12µA |
| Wire protocol | Nodes currently send **CSV-ish text** (`node_id,raw,temperature,epoch,L:<0\|1>`), not yet the packed-byte layout below — see [Data contract](#data-contract) |
| Data contract (`contracts/telemetry.md`) | Defined (v1, 13-byte packed layout) but not yet implemented on either end |
| Backend (`backend/`) | FastAPI stub (`/health` only) — the hub currently writes straight to Supabase, bypassing this service |
| Reconciliation (`backend/reconciliation/`) | Working, standalone script; recovers backfill after connectivity gaps |
| Database | Supabase-managed PostgreSQL, live: `readings`, `hub_status`, `instructions` tables |
| Frontend (`frontend/`) | Live dashboard — map, sensor cards, detail charts, hub status, drought forecast (nodes 1/4/5); English project page at `/about/` (description, results, history) and the Slovak Blue Challenge page at `/blue/`; deployed to Vercel |
| Model (`ml/`) | **Working drying + wetting models for nodes 1, 4, 5**, beating persistence at 7 days on every node; running live in the dashboard as a plant-stress forecast. The original combined bucket model still loses to persistence. See [The model](#the-model). |
| Node data recovery (`tools/`) | Pulls a node's LittleFS log over USB (sketch or read-only esptool script); used to backfill node 3 |
| Hardware (`hardware/`) | No KiCad sources committed yet — design lives in the deployed prototype and `hardware/bom.csv` |
| CI (`.github/workflows/`) | Firmware CI is real (`pio run` per sketch); backend/frontend/ml workflows are still placeholders |

---

## Architecture

```
[ capacitive soil sensor ]
          │
          ▼
[ node — ESP32, measure + pack + transmit ]
          │  LoRa (SX127x, 433MHz)
          ▼
[ hub — receive, buffer, upload ]
          │  internet
          ▼
[ database — Supabase/PostgreSQL ]
          │
          ▼
[ frontend — map + dashboard ]
```

The node spends nearly all its time as a transmitter only: it wakes, sends a reading, and
goes back to sleep without waiting for an acknowledgment. It listens for instructions
(config changes, `GETDATA` backfill requests) only in a short receive window every two
hours — full-time listening on the LoRa radio draws roughly 1000x the deep-sleep current,
so an always-on back channel wasn't an option on this power budget.

The design intent is that every layer reads the sensor payload in exactly the same format,
defined once in `contracts/telemetry.md` — see the note above: firmware hasn't migrated to
that packed-byte format yet, so today the layers actually agree on a plain CSV-ish line
instead. If firmware and backend ever silently disagree about the wire format, nothing
crashes — the data is just quietly wrong and downstream analysis (or a future model) trains
on it anyway. That's the failure mode the contract file exists to prevent once it's wired
up on both ends.

---

## Repository structure

```
dryahead/
├── docs/                 Written explanations and decisions (not code)
│   ├── adr/                  Architecture Decision Records — why we chose X over Y
│   └── model-design/         The scientific model: the *what & why* of the forecast
├── contracts/            The shared packed-byte data format (not yet live — see above)
├── hardware/             The physical device — bom.csv today; KiCad/CAD sources pending
│   ├── circuit/               KiCad schematic + PCB (not yet populated)
│   └── enclosure/             CAD/STL for the pipe enclosure + antenna mount (not yet populated)
├── firmware/             C++ (Arduino framework), PlatformIO-buildable — live on 4 field nodes
├── backend/              FastAPI service + the reconciliation/ backfill script
├── ml/                   Drought-model research (option_one/: FAO-56 bucket model)
├── frontend/             The live dashboard (React + Vite, plain JS/JSX)
├── tools/                Bench tools: pull a node's stored log over USB
│   ├── node_log_dump/        Arduino IDE sketch — flash temporarily, dumps LittleFS over serial
│   └── pull_node_log.py      Read-only alternative via esptool (no reflash)
├── node_dumps/           Raw logs pulled off nodes, plus what was uploaded from them
└── infra/                Placeholder — no containerized/deployed workflow yet
```

Each folder has its own `README.md`, and several have a `CLAUDE.md` noting what's real
versus aspirational in more detail than fits here.

---

## The sensor node

A battery-powered ESP32 node that wakes on a schedule, takes a reading, transmits it over
LoRa, and returns to deep sleep — sealed in a KG DN160 sewer-pipe enclosure chosen for cost
and mechanical ruggedness, buried/mounted in the field for a full season unattended.

**Core components**

- **MCU:** LaskaKit ESP32-DevKit
- **Radio:** LoRa, Semtech SX127x, 433 MHz
- **Real-time clock:** DS3231, wakes the board on a precise schedule via its `SQW` alarm
- **Soil sensor:** capacitive soil-moisture probe (no exposed electrodes, corrosion-resistant)
- **Power:** Li-Po 3000 mAh / 3.7 V pack, protected against deep discharge at 3.0 V

**Pin assignment**

| Function | Pin | Notes |
|----------|-----|-------|
| DS3231 SDA / SCL (I²C) | GPIO21 / GPIO22 | Real-time clock |
| DS3231 SQW → wake | GPIO33 | Alarm interrupt wakes the ESP32 from deep sleep |
| Soil moisture (analog) | GPIO34 | ADC1 input |
| Peripheral power gate | GPIO2 | Cuts power to sensor/radio between readings |
| LoRa SX127x | SPI (VSPI) | — |

Sleep/wake loop: the ESP32 sits in deep sleep drawing 11–12µA; the DS3231 alarm wakes it on
GPIO33; GPIO2 powers the sensor only for the measurement (limiting both idle draw and
electrolytic degradation of the sensor in the soil); the reading is read, sent over LoRa,
and also written to local flash (14-day retention) in case the transmission is missed; the
node returns immediately to deep sleep. That budget makes sleep current a non-issue in the
overall energy balance (~4% of daily draw) — the next efficiency gains are in cutting
redundant radio transmissions, not the sleep mode itself.

---

## Data contract

`contracts/telemetry.md` defines the intended 13-byte packed wire format (`packet_version`,
`node_id`, `timestamp`, raw + calibrated soil moisture, battery voltage, optional
temperature). **This is not what's on the air today** — firmware still sends CSV-ish text
and the backend has no decoder for the packed format yet. Migrating to it requires changing
firmware, the backend, and a golden fixture together in one change (see the
`telemetry-contract` workflow) — never done piecemeal, since a silent field/format mismatch
between producer and consumer corrupts data without crashing anything.

---

## The model

The intended approach is **forecast-primary**: the backbone of the prediction is the
weather forecast, and field readings are used to correct and anchor it to real local
conditions via data assimilation — a forecast alone doesn't know a specific plot's soil
state, and a sensor alone can't see the future.

A first version runs today, built in `ml/option_one/` for nodes 1, 4 and 5 and split
into two physically-based models fitted per node on raw sensor counts, with the local
meteotekov weather station as ground truth:

- **Drying model** (`drydown.py`) — how the reading rises (dries) between wettings: drainage
  above field capacity, then stress-limited evapotranspiration from station Penman-Monteith
  ET0. Five parameters per node.
- **Wetting model** (`wetting.py`) — how far the reading drops when rain falls: a top-layer
  store for node 4 (first ~4.4 mm held, then ~98 counts/mm), linear for node 5 (~11 counts/mm).
  Node 1 doesn't respond predictably to station rain, so it has no wetting model.

Held-out 7-day RMSE in raw counts (fitted 2026-07-01 → 09-25, validation from 08-30;
5–9 forecasts per node, so indicative):

| Node | Drying model | Persistence | Average drift |
|------|-------------:|------------:|--------------:|
| 1 | **9.5** | 14.9 | 26.6 |
| 4 | **8.6** | 59.4 | 69.5 |
| 5 | **8.0** | 47.5 | 20.7 |

The drying model beats both baselines on every node. The dashboard runs both models in the
browser (`frontend/src/lib/droughtForecast.js`, parameters exported to
`frontend/src/data/droughtModel.json`) on Open-Meteo's 16-day forecast. Each sensor card
shows when the node reaches **plant stress** if no rain falls, and the detail modal adds a
with-forecast-rain line.

Caveats: fitted on summer only, so autumn/winter drying is extrapolation, and the models
should be refitted as the record grows. The original combined FAO-56 bucket model
(`run_pipeline.py`) is kept as a baseline; it still loses to persistence. See
`ml/option_one/README.md` for the full methodology and `docs/model-design/README.md` for
how it fits the broader forecast-primary design.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Firmware | PlatformIO · ESP32 · Arduino framework — `pio run` per sketch (`nodes/node_with_rtc`, `nodes/node_no_rtc`, `hub`) |
| Radio | LoRa, Semtech SX127x, 433 MHz |
| Backend | Python 3.12 · FastAPI · SQLAlchemy · Alembic · psycopg (configured; ingestion not yet implemented) |
| Reconciliation | Standalone Python script, direct Supabase REST calls (anon key + RLS) |
| Database | Supabase-managed PostgreSQL |
| ML | Python 3.12 · NumPy/SciPy/pandas (`option_one`) · DVC planned for data/model versioning (not yet initialized) |
| Frontend | React 19 · Vite · plain JavaScript/JSX (**not** TypeScript, despite earlier drafts of this README) · Tailwind CSS · Leaflet · Recharts |
| Hosting | Frontend on Vercel; backend/hub not yet containerized |
| CI | GitHub Actions, path-filtered per component — firmware's is real, the rest are placeholders |
| Large files | git-lfs staged for hardware binaries (none committed yet) |

---

## Roadmap

Priorities below come directly from what the field deployment surfaced, not hypothetical
features:

1. **Seal the enclosure properly** — IP67 with cable glands and a gasketed antenna
   feedthrough, plus a checked solder/assembly step before deployment. The two real hardware
   failures in 105 days were both build-quality problems. Node 3's antenna chamber let water
   in, which stopped transmission. Node 2's bad solder joint kept it out of deep sleep, and
   the repair destroyed the board. Node 3's DS3231 dropping out in the midday heat points
   the same way. Mechanical/build quality is the weakest link so far, not firmware, radio
   or cloud.
2. **Fix the double wake per cycle** — nodes log two readings 8–13 s apart in most
   20-minute slots, doubling flash use and radio time for no extra information.
3. **Migrate the wire format** to `contracts/telemetry.md`'s packed-byte layout, with a
   golden fixture shared by firmware and backend (see `telemetry-contract`).
4. **Wire the FastAPI backend into the live ingestion path** — today the hub writes to
   Supabase directly; the backend only exposes `/health`.
5. **Add a firmware diagnostic channel** (battery voltage, reset reason, sensor health) —
   node 2's slow drain and RTC resets would have been visible in days instead of only
   after failure.
6. **Extend node local-storage retention** past 14 days, since the one tested outage lost
   77% of its missed readings once reconciliation ran later than that window.
7. **Volumetric sensor calibration** against a reference method, per soil type — current
   readings track relative change only.
8. **Second deployment site** with a different soil type, to give the model something to
   generalize across before data-driven modelling is worth attempting.

---

## The name

**DryAhead** — a drought forecast is a warning that dry conditions lie *ahead*, and a good
early-warning system keeps you a step *ahead* of them. Say it out loud and it also reads as
"dry ahead": that's the whole product in two words.
