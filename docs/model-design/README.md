# Model design

This folder holds the **scientific** design of the drought-prediction model: what the model
predicts, why it's structured the way it is, and the reasoning behind the approach. It's the
*what and why*.

It's deliberately separate from `ml/`, which holds the *how* — the actual training code, data
pipelines, and experiment tracking that implement the design described here.

## Scope

The model is **forecast-primary**: its main job is producing a forward-looking drought forecast,
not just describing current conditions. It's expected to use **data assimilation** — combining
the live stream of sensor readings (soil moisture, etc. from `contracts/telemetry.md`) with
whatever external data sources (weather forecasts, historical climate data, satellite indices)
improve the forecast — to continually correct its state as new sensor data arrives, rather than
producing a single static prediction from a fixed dataset.

Document here, as the design solidifies:
- What exactly the model predicts (horizon, drought index/definition used, output format).
- What inputs it assimilates and at what cadence.
- The rationale for model choice (e.g. why a particular class of model fits sparse, noisy,
  field-sensor data).
- Validation approach — how "is this forecast any good" will be evaluated against ground truth.

This is a stub — fill in as the science gets designed.

## Candidate approaches under evaluation

- **Option 1** (`ml/option_one/`): a physically-based FAO-56 root-zone bucket model (rain,
  drainage, and crop-stressed evapotranspiration simulated at daily steps), calibrated per node
  against real sensor data with differential evolution, scored by KGE against a persistence
  baseline. Produces an ensemble forecast (via Open-Meteo's weather ensemble) and an Available
  Water Fraction drought index. See `ml/option_one/README.md` for the full design rationale and
  its known limitations — notably that the live dataset as of 2026-09 is only ~2 months deep
  (well short of the ~1 year this method assumes), so early calibration runs are data-starved and
  should be read as a pipeline shakedown, not a validated model.
