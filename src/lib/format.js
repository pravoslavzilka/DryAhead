export function timeAgo(ms) {
  if (ms == null) return 'never'
  const diff = Date.now() - ms
  if (diff < 0) return 'just now'
  const min = Math.floor(diff / 60000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  const h = Math.floor(min / 60)
  if (h < 24) return `${h} h ${min % 60} min ago`
  const d = Math.floor(h / 24)
  return `${d} d ${h % 24} h ago`
}

export function fmtDateTime(ms) {
  return new Date(ms).toLocaleString([], {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

export function fmtTick(ms, rangeHours) {
  const d = new Date(ms)
  if (rangeHours <= 48) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' })
}

export function fmtPct(v, digits = 0) {
  return v == null ? '—' : `${v.toFixed(digits)} %`
}

export function fmtTemp(v) {
  return v == null ? '—' : `${v.toFixed(1)} °C`
}

const MIN_PLAUSIBLE_MS = Date.UTC(2020, 0, 1)
const CLOCK_SLACK_MS = 60 * 1000

/**
 * Epoch ms for a reading. `recorded_at` (unix seconds, node clock) is preferred —
 * it is correct for backlogged readings — but node clocks drift, and some rows
 * carry timestamps in the future or near epoch. A reading cannot be recorded
 * after the server received it, so anything later than `received_at` (or before
 * 2020) falls back to the trustworthy server timestamp.
 */
export function readingTime(r) {
  const rec = r.recorded_at != null ? r.recorded_at * 1000 : null
  const recv = r.received_at ? Date.parse(r.received_at) : null
  if (rec != null && rec >= MIN_PLAUSIBLE_MS && (recv == null || rec <= recv + CLOCK_SLACK_MS)) {
    return rec
  }
  return recv ?? null
}
