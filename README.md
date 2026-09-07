# DryAhead

**A soil-moisture sensor network monitoring drought risk in the field — live since June 2026.**

DryAhead measures soil moisture in the field, carries it over long-range LoRa radio to a
cloud database, and shows it on a live dashboard. The eventual goal is to fuse those
readings with weather forecasts to predict drought stress *before* it happens — the name
says the goal: see the dry conditions **ahead** of time, while there's still time to act.
That predictive layer is still being designed; what exists today is the sensing and
delivery pipeline it depends on, deployed and running in the field.

Live dashboard: **[dryahead.com](https://dryahead.com/)**

---

## Field deployment

Five nodes and a hub have been running unattended near Zaježová (Pliešovce, Slovakia)
since **2026-06-29**, across five points within a 500 m radius. As of **2026-09-06** (69
days in):

| Node | Status | Delivered slots | Delivery rate |
|------|--------|-----------------:|---------------:|
| 1 | in operation | 3,572 / 4,998 | 71.5% |
| 2 | **dead** — solder fault kept it out of deep sleep, drained the battery, damaged further during a repair attempt | 389 / 2,904 | 13.4% |
| 3 | **silent since 2026-09-01** — water ingress in the antenna chamber degraded the radio link below the hub's decode threshold | 1,993 / 4,668 | 42.7% |
| 4 | in operation | 4,093 / 4,998 | 81.9% |
| 5 | in operation | 4,107 / 4,999 | 82.2% |
| **Total** | | **14,154 / 22,567** | **62.7%** |

The two nodes without a hardware fault (4 and 5) deliver ~83%, so the network's ceiling is
set by enclosure/mechanical reliability, not the radio link or cloud stack — LoRa RSSI held
between −95 and −97 dBm with no observed distance dependence within 1 km. Root CLAUDE.md
tracks this as "4 LoRa nodes live in the field" — node 2 is no longer recoverable.

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
| Frontend (`frontend/`) | Live dashboard — map, sensor cards, detail charts, hub status, deployed to Vercel |
| Model (`ml/`) | Physically-based bucket model pipeline built and run against live data; not yet beating a persistence baseline — data-volume problem (~2 months live), not a physics problem. See `ml/option_one/README.md`. |
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

That layer isn't running yet. The first candidate, `ml/option_one/` — a physically-based
FAO-56 root-zone bucket model, calibrated per node with differential evolution and scored
by KGE against a persistence baseline — has been built and run against the live Supabase
data. As of the last run (2026-09-03) it loses to the persistence baseline at every
forecast horizon on every node. That's read as a data-volume problem, not a sign the
physics is wrong: the live record is only ~2 months deep (node 2 effectively 8 days) against
9 free parameters, and a synthetic two-year test of the same pipeline recovers known
parameters cleanly. See `ml/option_one/README.md` for the full methodology and
`docs/model-design/README.md` for how it fits the broader forecast-primary design.

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
   feedthrough. Node 3's failure (water in the antenna chamber) and node 2's (a solder
   fault that only showed up in the field) were the two real hardware failures in 69 days;
   mechanical/build quality is the weakest link so far, not firmware, radio, or cloud.
2. **Migrate the wire format** to `contracts/telemetry.md`'s packed-byte layout, with a
   golden fixture shared by firmware and backend (see `telemetry-contract`).
3. **Wire the FastAPI backend into the live ingestion path** — today the hub writes to
   Supabase directly; the backend only exposes `/health`.
4. **Add a firmware diagnostic channel** (battery voltage, reset reason, sensor health) —
   node 2's slow drain and RTC resets would have been visible in days instead of only
   after failure.
5. **Extend node local-storage retention** past 14 days, since the one tested outage lost
   77% of its missed readings once reconciliation ran later than that window.
6. **Volumetric sensor calibration** against a reference method, per soil type — current
   readings track relative change only.
7. **Second deployment site** with a different soil type, to give the model something to
   generalize across before data-driven modelling is worth attempting.

---

## The name

**DryAhead** — a drought forecast is a warning that dry conditions lie *ahead*, and a good
early-warning system keeps you a step *ahead* of them. Say it out loud and it also reads as
"dry ahead": that's the whole product in two words.
