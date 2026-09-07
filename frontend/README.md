# Drought Monitor — frontend

React + Vite + Tailwind dashboard for the soil-humidity sensor network. Reads
live data from Supabase (`sensor_calibration` + `readings`) with the public
anon key.

## Run

```sh
npm install
npm run dev       # http://localhost:5173
npm run build     # production bundle in dist/
```

Credentials live in `.env` (see `.env.example`). Only the **anon** key belongs
here — never the service_role key.

## What it shows

- **Map** (OpenStreetMap/Leaflet): one pin per sensor with current humidity and
  status color; critical pins pulse and carry a ⚠ badge. Popup → details.
- **Sensor cards**: one per row in `sensor_calibration` (new nodes appear
  automatically), with current humidity, temperature, last-reading age, a 48 h
  sparkline and the dry-soil guide. Click → detail modal.
- **Detail modal**: interactive humidity chart (24 h – 90 d ranges, tooltip,
  brush zoom) with dashed guides at the dry-soil and wet-soil calibration
  points, a separate temperature chart, and the raw calibration values.
  Deep-linkable via `#sensor-<node_id>`.
- **Hub status card** (`HubStatusCard`): the hub's own heartbeat history (168 h)
  as a bar chart, with an Online/Offline/issue-reported badge — the thing that
  tells you whether a quiet sensor means "no rain" or "the hub is offline."
- **Reception activity** (`ReceptionActivity`): a GitHub-style delivery
  heatmap — received vs. expected readings per day/week/month bucket, per
  node — for spotting delivery gaps like the ones described in the root
  README's field-deployment table at a glance.
- **Instructions widget** (`InstructionsWidget`): outstanding/recent
  `GETDATA` backfill instructions and their state, surfacing what
  `backend/reconciliation/` has queued or resolved.
- **Weather strip** (`WeatherStrip`): local forecast context alongside the
  sensor readings.
- **About page**: project background for a visitor landing on the dashboard
  cold.
- Data auto-refreshes every 5 minutes (sensors report every ~20 min).

## Data handling notes

- **Humidity calibration**: linear map of `raw` with `air` → 0 % and
  `water` → 100 %, clamped. `dry_soil` / `wet_soil` are converted to the same
  scale and drawn as chart guides; a sensor at/below the dry-soil level is
  flagged **Extremely dry** (alert banner + pulsing map pin).
- **Timestamps**: node clocks drift (some `recorded_at` values are in the
  future), so queries filter/order on the server-side `received_at`;
  `recorded_at` is used for chart x-positions only when plausible
  (`src/lib/format.js → readingTime`).
- **Status**: stale after 60 min of silence · critical ≤ dry-soil % · dry within
  10 points above it · saturated ≥ wet-soil %.
- Queries paginate past PostgREST's 1000-row cap (`src/lib/supabase.js`).
