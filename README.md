# drought-platform

A monorepo for a drought-prediction platform. Field sensor nodes measure soil moisture and send
readings over LoRa to a gateway; a backend ingests and stores the readings, and a machine-learning
model turns the history into a forecast-primary drought prediction shown in a web app.

The project spans six domains, each with its own top-level folder:

- **`hardware/`** — the physical sensor node: circuit design (KiCad) and the enclosure/CAD for
  mounting it in the field.
- **`firmware/`** — the ESP32 code that runs on the sensor node: reads the soil moisture sensor,
  timestamps it with the RTC, and sends it over LoRa.
- **`ml/`** — training code and experiments for the drought-prediction model, plus data/model
  tracking via DVC.
- **`backend/`** — the FastAPI service that receives LoRa-relayed readings, stores them in
  Postgres, and serves predictions to the frontend.
- **`frontend/`** — the React web app that displays sensor data and drought forecasts.
- **`docs/`** (in particular `docs/model-design/`) — the scientific design of the prediction
  model: the *what and why*, as opposed to `ml/`'s *how*.

`contracts/` is not one of the six domains, but it's the most important folder in the repo: it's
the shared data definition (the LoRa telemetry packet layout) that firmware and backend both
depend on. Change it carefully, and change both sides together.
