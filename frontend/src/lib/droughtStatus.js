/**
 * Drought status and trend per node. Everything here works on raw counts
 * (higher raw = drier).
 *
 * One dry limit per node:
 *   modelled nodes -> the drying model's plant-stress line (an estimate, not
 *                     validated against plants)
 *   other nodes    -> the stored dry_soil value (a rough number)
 */
import { nodeModel, currentRaw } from './droughtForecast'

const DAY_MS = 86400000
// "getting dry" starts this share of the air-water span before the limit
const NEAR_LIMIT_SHARE = 0.1
// day-to-day median changes are typically 6-16 counts on the field nodes
const STEADY_COUNTS = 15

export function dryLimit(nodeId, cal) {
  const m = nodeModel(nodeId)
  if (m) return { raw: m.stress_raw, modelled: true }
  return cal?.dry_soil != null ? { raw: cal.dry_soil, modelled: false } : null
}

/** `raw` should be the 24 h median where there is one, as the forecast uses. */
export function sensorStatus(raw, limit, cal, lastSeenMs, staleAfterMs) {
  if (lastSeenMs == null || Date.now() - lastSeenMs > staleAfterMs) return 'stale'
  if (raw == null || limit == null) return 'unknown'
  if (raw >= limit.raw) return limit.modelled ? 'stress' : 'verydry'
  if (cal?.air != null && cal?.water != null
    && raw >= limit.raw - NEAR_LIMIT_SHARE * (cal.air - cal.water)) return 'drying'
  return 'moist'
}

/** Last 24 h median against the 24 h before it: 'drier' | 'wetter' | 'steady' | null. */
export function rawTrend(history) {
  if (!history?.length) return null
  const end = history.at(-1).t
  const now = currentRaw(history)
  const before = currentRaw(history.filter((p) => p.t <= end - DAY_MS))
  if (now == null || before == null) return null
  if (now - before > STEADY_COUNTS) return 'drier'
  if (before - now > STEADY_COUNTS) return 'wetter'
  return 'steady'
}

export const TREND_LABEL = {
  drier: '↘ Getting drier',
  wetter: '↗ Getting wetter',
  steady: '→ Steady',
}

export function trendText(trend) {
  return TREND_LABEL[trend] ?? 'Not enough data for a trend'
}
