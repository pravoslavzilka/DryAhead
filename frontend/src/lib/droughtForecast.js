import model from '../data/droughtModel.json'
import { rawToHumidity } from './calibration'

/**
 * Drought forecast for the modelled nodes (1, 4, 5), run in the browser.
 *
 * Port of ml/option_one's drying model (drydown.py, single-rate variant) and
 * wetting model (wetting.py), with parameters from src/data/droughtModel.json
 * (written by ml/option_one/export_frontend_model.py — re-export after
 * refitting). Works in raw sensor counts; on these sensors higher raw = drier.
 *
 * "Plant stress" is where the drying model's stress factor starts dropping:
 * past it, soil is dry enough that plants struggle to pull water and drying
 * slows down. Per node: raw_fc + p * (raw_wp - raw_fc).
 */

const DAY_MS = 86400000
const START_WINDOW_MS = DAY_MS // current state = median raw over the last 24 h
const MIN_START_READINGS = 6

export const MODEL_INFO = model

export function nodeModel(nodeId) {
  return model.nodes[String(nodeId)] ?? null
}

/** Median raw of the last 24 h of `history` ([{t, raw}]), or null if too sparse. */
export function currentRaw(history) {
  if (!history?.length) return null
  const end = history.at(-1).t
  const raws = history.filter((p) => p.raw != null && p.t > end - START_WINDOW_MS).map((p) => p.raw)
  if (raws.length < MIN_START_READINGS) return null
  raws.sort((a, b) => a - b)
  const mid = Math.floor(raws.length / 2)
  return raws.length % 2 ? raws[mid] : (raws[mid - 1] + raws[mid]) / 2
}

/** One day of drying (drydown.simulate): drainage above field capacity, then Ks * a * ET0. */
function dryStep(x, et0, d) {
  const taw = d.raw_wp - d.raw_fc
  const rawThr = d.p * taw
  if (x < d.raw_fc) x += (d.raw_fc - x) * (1 - Math.exp(-1 / d.tau_d))
  const depletion = Math.max(x - d.raw_fc, 0)
  const ks = depletion <= rawThr ? 1 : Math.max((taw - depletion) / (taw - rawThr), 0)
  const prev = x
  x += ks * Math.max(d.a * et0, 0)
  if (x > d.raw_wp && prev <= d.raw_wp) x = d.raw_wp
  return x
}

/** mm of a day's rain that reaches the sensor, and the top-layer store after it (wetting.py). */
function throughRain(rain, et0, store, w) {
  if (w.model === 'linear') return { through: rain, store }
  if (w.model !== 'store') return { through: 0, store }
  let s = store + rain
  const over = Math.max(s - w.s_top, 0)
  s -= over
  return { through: over, store: Math.max(s - et0, 0) }
}

/**
 * Forecast one node from `x0` (raw, as of `t0`) over the weather `days`
 * ([{date: 'YYYY-MM-DD', et0, rain}], station-scale ET0, local days, today
 * at index `todayIdx`, earlier days used only to fill the rain store).
 * Returns { points: [{t, raw}], stressAt: ms | null, stressedNow }.
 */
export function forecastNode(nodeId, x0, t0, days, todayIdx, { withRain }) {
  const m = nodeModel(nodeId)
  if (!m || x0 == null || todayIdx < 0) return null
  const { drying, wetting, stress_raw: stress } = m

  let store = 0
  if (withRain) {
    for (let i = 0; i < todayIdx; i++) store = throughRain(days[i].rain, days[i].et0, store, wetting).store
  }

  const points = [{ t: t0, raw: x0 }]
  let x = x0
  let stressAt = x0 >= stress ? t0 : null
  for (let i = todayIdx; i < days.length; i++) {
    if (withRain) {
      const r = throughRain(days[i].rain, days[i].et0, store, wetting)
      store = r.store
      x -= Math.min((wetting.gain ?? 0) * r.through, Math.max(x - wetting.floor, 0))
    }
    // a reading sits mid-day, so each step spans half of today and half of tomorrow
    const et0 = i + 1 < days.length ? (days[i].et0 + days[i + 1].et0) / 2 : days[i].et0
    const prev = x
    x = dryStep(x, et0, drying)
    const t = t0 + (i - todayIdx + 1) * DAY_MS
    if (stressAt == null && prev < stress && x >= stress) {
      stressAt = t - DAY_MS + ((stress - prev) / (x - prev)) * DAY_MS
    }
    points.push({ t, raw: x })
  }
  return { points, stressAt, stressedNow: x0 >= stress }
}

/** Plant-stress threshold on the dashboard's 0-100 % scale. */
export function stressPct(nodeId, cal) {
  const m = nodeModel(nodeId)
  return m ? rawToHumidity(m.stress_raw, cal) : null
}
