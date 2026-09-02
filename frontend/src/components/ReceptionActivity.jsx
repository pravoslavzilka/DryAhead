import { useState } from 'react'
import {
  useReceptionActivity, GRANULARITIES, BUCKET_COUNT_OPTIONS, DEFAULT_BUCKET_COUNT,
  MODES, DEFAULT_MODE,
} from '../hooks/useReceptionActivity'

// One square is ~24px (20px on narrow screens) including its gap; the label
// column plus card padding eats roughly 200px of the viewport.
function pickDefaultBucketCount() {
  if (typeof window === 'undefined') return DEFAULT_BUCKET_COUNT
  const width = Math.min(window.innerWidth, 1152)
  const perSquare = width >= 640 ? 24 : 20
  const fit = Math.floor((width - 200) / perSquare)
  const eligible = BUCKET_COUNT_OPTIONS.filter((n) => n <= fit)
  return eligible.length ? eligible.at(-1) : BUCKET_COUNT_OPTIONS[0]
}

// Blue -> yellow -> red by share of expected readings received; grey means nothing came in at all.
const LEVELS = [
  { min: 0.75, color: '#2a78d6', label: 'Full' },
  { min: 0.35, color: '#fab219', label: 'Partial' },
  { min: 0, color: '#d03b3b', label: 'Sparse' },
]
const NO_DATA = { color: '#a8a29e', label: 'No data' }

function levelFor(count, ratio) {
  if (count === 0) return NO_DATA
  return LEVELS.find((l) => ratio >= l.min) ?? LEVELS.at(-1)
}

function fmtDay(ms) {
  return new Date(ms).toLocaleDateString([], { day: 'numeric', month: 'short' })
}

function bucketLabel(bucket, granularityKey) {
  if (granularityKey === 'day') return fmtDay(bucket.start)
  return `${fmtDay(bucket.start)} – ${fmtDay(bucket.end - 1)}`
}

export default function ReceptionActivity() {
  const [granularity, setGranularity] = useState('day')
  const [bucketCount, setBucketCount] = useState(pickDefaultBucketCount)
  const [mode, setMode] = useState(DEFAULT_MODE)
  const { rows, loading, error } = useReceptionActivity(granularity, bucketCount, mode)

  return (
    <section className="mb-6 rounded-2xl border border-orange-100 bg-white p-4 shadow-sm">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Reception activity
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-stone-500">Show</span>
            {BUCKET_COUNT_OPTIONS.map((n) => (
              <button
                key={n}
                onClick={() => setBucketCount(n)}
                className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${
                  n === bucketCount
                    ? 'bg-orange-600 text-white shadow-sm'
                    : 'bg-orange-50 text-stone-600 hover:bg-orange-100'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
          <div className="flex gap-1.5">
            {GRANULARITIES.map((g) => (
              <button
                key={g.key}
                onClick={() => setGranularity(g.key)}
                className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                  g.key === granularity
                    ? 'bg-orange-600 text-white shadow-sm'
                    : 'bg-orange-50 text-stone-600 hover:bg-orange-100'
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-stone-500">By</span>
            {MODES.map((m) => (
              <button
                key={m.key}
                onClick={() => setMode(m.key)}
                title={
                  m.key === 'recorded'
                    ? 'When the node says it took the reading — backfilled data fills in the day it covers, but past cells can change later'
                    : 'When the server received the reading — stable over time, but a backfill shows up on the day it was resent, not the day it covers'
                }
                className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                  m.key === mode
                    ? 'bg-orange-600 text-white shadow-sm'
                    : 'bg-orange-50 text-stone-600 hover:bg-orange-100'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <p className="mb-3 text-xs text-stone-400">
        Past {bucketCount} {GRANULARITIES.find((g) => g.key === granularity).label.toLowerCase()} · how much data each node delivered
        {mode === 'recorded' ? ', by when it was recorded' : ', by when it arrived'}
      </p>

      {error && (
        <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          Failed to load activity: {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-6 animate-pulse rounded bg-orange-100/60" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="text-sm text-stone-500">No sensors to show activity for.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="border-separate border-spacing-y-1.5 text-sm">
            <tbody>
              {rows.map(({ nodeId, buckets }) => (
                <tr key={nodeId}>
                  <td className="whitespace-nowrap pr-3 text-xs font-medium text-stone-600">
                    Sensor {nodeId}
                  </td>
                  {buckets.map((b, i) => {
                    const level = levelFor(b.count, b.ratio)
                    return (
                      <td key={i} className="px-0.5">
                        <div
                          title={`${bucketLabel(b, granularity)} — ${b.count} reading${b.count === 1 ? '' : 's'} (${level.label})`}
                          className="h-4 w-4 rounded-sm sm:h-5 sm:w-5"
                          style={{ background: level.color }}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-stone-500">
        {[...LEVELS, NO_DATA].map((l) => (
          <span key={l.label} className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: l.color }} />
            {l.label}
          </span>
        ))}
      </div>
    </section>
  )
}
