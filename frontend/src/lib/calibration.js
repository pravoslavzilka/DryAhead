/**
 * Calibration: `air` and `water` are the raw-value extremes.
 *   air   -> 0 % humidity (bone dry)
 *   water -> 100 % humidity (submerged)
 * The mapping is linear and direction-agnostic (works whether raw rises or
 * falls with moisture), clamped to 0–100.
 */
export function rawToHumidity(raw, cal) {
  if (raw == null || cal?.air == null || cal?.water == null || cal.air === cal.water) return null
  const pct = ((cal.air - raw) / (cal.air - cal.water)) * 100
  return Math.min(100, Math.max(0, pct))
}

/** dry_soil / wet_soil expressed on the same 0–100 % scale, for chart guides + alerts. */
export function thresholds(cal) {
  return {
    dryPct: rawToHumidity(cal?.dry_soil, cal),
    wetPct: rawToHumidity(cal?.wet_soil, cal),
  }
}

export const STATUS_META = {
  critical: { label: 'Extremely dry', color: '#d03b3b', badge: 'bg-red-100 text-red-700 border-red-200' },
  dry: { label: 'Dry', color: '#ec835a', badge: 'bg-orange-100 text-orange-700 border-orange-200' },
  ok: { label: 'Normal', color: '#0ca30c', badge: 'bg-green-100 text-green-700 border-green-200' },
  wet: { label: 'Saturated (mud)', color: '#2a78d6', badge: 'bg-blue-100 text-blue-700 border-blue-200' },
  stale: { label: 'No recent data', color: '#a8a29e', badge: 'bg-stone-100 text-stone-500 border-stone-200' },
  unknown: { label: 'Unknown', color: '#a8a29e', badge: 'bg-stone-100 text-stone-500 border-stone-200' },
}

const STALE_AFTER_MS = 60 * 60 * 1000 // sensors report every 20 min; 3 missed cycles = stale

export function sensorStatus(humidity, { dryPct, wetPct }, lastSeenMs) {
  if (lastSeenMs == null || Date.now() - lastSeenMs > STALE_AFTER_MS) return 'stale'
  if (humidity == null) return 'unknown'
  if (dryPct != null && humidity <= dryPct) return 'critical'
  if (dryPct != null && humidity <= dryPct + 10) return 'dry'
  if (wetPct != null && humidity >= wetPct) return 'wet'
  return 'ok'
}
