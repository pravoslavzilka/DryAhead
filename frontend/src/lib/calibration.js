/**
 * Raw ADC -> estimated soil water content (% by volume). PROVISIONAL.
 *
 * Do all maths (averages, thresholds, forecasts) on raw counts and convert
 * only for display: the curve is not linear.
 *
 * From the 2026-11-22 bench run (tools/soil_calibration/vwc_convert.py,
 * data/vwc_model_water50.json): one soil, 3 bench sensors, one run.
 *   0 %  = bench oven-dry reading (mean of the 3 bench sensors, not the nodes)
 *   50 % = the node's `water` reading (assumed value, not measured)
 * Measured up to 26.5 %; above that the curve is interpolated.
 */
const RAW_OVEN_DRY = 3242.4
const WATER_PCT = 50
const TAU = 20.62

/** Top of the display scale, for chart axes. */
export const MAX_WATER_CONTENT = WATER_PCT

export function rawToWaterContent(raw, cal) {
  if (raw == null || cal?.water == null || cal.water >= RAW_OVEN_DRY) return null
  const g = Math.min(1, Math.max(0, (RAW_OVEN_DRY - raw) / (RAW_OVEN_DRY - cal.water)))
  return -TAU * Math.log(1 - g * (1 - Math.exp(-WATER_PCT / TAU)))
}

export const STATUS_META = {
  stress: { label: 'Estimated stress', color: '#d03b3b', badge: 'bg-red-100 text-red-700 border-red-200' },
  verydry: { label: 'Very dry (rough limit)', color: '#d03b3b', badge: 'bg-red-100 text-red-700 border-red-200' },
  drying: { label: 'Getting dry', color: '#ec835a', badge: 'bg-orange-100 text-orange-700 border-orange-200' },
  moist: { label: 'Moist', color: '#0ca30c', badge: 'bg-green-100 text-green-700 border-green-200' },
  stale: { label: 'No recent data', color: '#a8a29e', badge: 'bg-stone-100 text-stone-500 border-stone-200' },
  unknown: { label: 'Unknown', color: '#a8a29e', badge: 'bg-stone-100 text-stone-500 border-stone-200' },
}

export const isAlertStatus = (status) => status === 'stress' || status === 'verydry'

const REPORT_INTERVAL_MIN = 20
export const STALE_AFTER_MS = 3 * REPORT_INTERVAL_MIN * 60 * 1000 // 3 missed cycles = stale

/** Expected readings for a node in a full day, given its ~20 min report cadence. */
export const READINGS_PER_DAY = (24 * 60) / REPORT_INTERVAL_MIN
