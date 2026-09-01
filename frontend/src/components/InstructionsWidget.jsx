import { useState } from 'react'
import { useInstructions } from '../hooks/useInstructions'
import { timeAgo, fmtDateTime } from '../lib/format'

const STATE_META = {
  Posted: { label: 'Posted', badge: 'bg-blue-100 text-blue-700 border-blue-200' },
  Received: { label: 'Received', badge: 'bg-orange-100 text-orange-700 border-orange-200' },
  Resolved: { label: 'Resolved', badge: 'bg-green-100 text-green-700 border-green-200' },
  'Failed to resolve': { label: 'Failed', badge: 'bg-red-100 text-red-700 border-red-200' },
}
const UNKNOWN_STATE = { label: 'Unknown', badge: 'bg-stone-100 text-stone-500 border-stone-200' }

function stateMeta(state) {
  return STATE_META[state] ?? UNKNOWN_STATE
}

function fmtEpoch(sec) {
  return sec == null ? '—' : fmtDateTime(sec * 1000)
}

export default function InstructionsWidget() {
  const [open, setOpen] = useState(false)
  const { instructions, activeCount, failedCount, loading, error } = useInstructions()

  const toneClass = failedCount > 0
    ? 'border-red-200 text-red-700'
    : activeCount > 0
      ? 'border-orange-200 text-orange-700'
      : 'border-green-200 text-green-700'

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="View instruction queue"
        className={`fixed right-0 top-1/2 z-40 flex -translate-y-1/2 flex-col items-center gap-1 rounded-l-2xl border border-r-0 bg-white px-3 py-4 shadow-md transition hover:px-4 ${toneClass}`}
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide [writing-mode:vertical-rl]">
          Instructions
        </span>
        <span className="text-lg font-bold leading-none">{loading ? '…' : activeCount}</span>
        {failedCount > 0 && (
          <span className="text-[10px] font-semibold text-red-700">{failedCount} failed</span>
        )}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-stone-900/50 p-4 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <div
            className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-y-auto rounded-2xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Instruction queue details"
          >
            <div className="flex items-start justify-between gap-4 border-b border-orange-100 bg-gradient-to-r from-red-50 to-orange-50 px-6 py-4">
              <div>
                <h2 className="text-xl font-bold text-stone-800">Instruction queue</h2>
                <p className="mt-0.5 text-xs text-stone-500">
                  Backfill commands sent to the hub · {activeCount} in flight
                  {failedCount > 0 ? ` · ${failedCount} failed` : ''}
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="rounded-full p-1.5 text-stone-500 hover:bg-orange-100 hover:text-stone-800"
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            <div className="px-6 py-5">
              {error && (
                <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  Failed to load instructions: {error}
                </div>
              )}
              {loading ? (
                <div className="space-y-2">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="h-14 animate-pulse rounded-xl bg-orange-100/60" />
                  ))}
                </div>
              ) : instructions.length === 0 ? (
                <p className="text-sm text-stone-500">No instructions have been issued yet.</p>
              ) : (
                <div className="space-y-2">
                  {instructions.map((i) => {
                    const meta = stateMeta(i.state)
                    return (
                      <div key={i.id} className="rounded-xl border border-orange-100 bg-orange-50/50 px-3 py-2.5">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-stone-700">Sensor {i.node_id}</span>
                            <span className="text-xs text-stone-400">{i.command}</span>
                          </div>
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${meta.badge}`}>
                            {meta.label}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-stone-500">
                          Since {fmtEpoch(i.range_start)}
                          {i.range_end != null ? ` – ${fmtEpoch(i.range_end)}` : ''}
                        </div>
                        {i.message && <div className="mt-1 text-xs text-red-600">{i.message}</div>}
                        <div className="mt-1 text-[11px] text-stone-400">
                          Created {timeAgo(Date.parse(i.created_at))}
                          {i.updated_at && i.updated_at !== i.created_at
                            ? ` · updated ${timeAgo(Date.parse(i.updated_at))}`
                            : ''}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
