import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { useHubStatus } from '../hooks/useHubStatus'
import { timeAgo, fmtUptime, fmtTick, fmtDateTime } from '../lib/format'

const HISTORY_HOURS = 168

function badgeFor(health) {
  if (!health) return { label: 'Unknown', badge: 'bg-stone-100 text-stone-500 border-stone-200' }
  if (!health.healthy) return { label: 'Offline', badge: 'bg-red-100 text-red-700 border-red-200' }
  if (health.last_error) return { label: 'Online · issue reported', badge: 'bg-orange-100 text-orange-700 border-orange-200' }
  return { label: 'Online', badge: 'bg-green-100 text-green-700 border-green-200' }
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl bg-orange-50/70 px-3 py-2">
      <div className="text-[11px] text-stone-500">{label}</div>
      <div className="text-lg font-bold text-stone-800">{value}</div>
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-lg border border-orange-100 bg-white/95 px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-semibold text-stone-700">{fmtDateTime(label)}</div>
      <div className="text-stone-600">
        Pending: <span className="font-semibold">{p.pending_count}</span>
      </div>
      {p.wifi_rssi != null && <div className="text-stone-400">WiFi {p.wifi_rssi} dBm</div>}
      {p.last_error && <div className="mt-1 text-red-600">{p.last_error}</div>}
    </div>
  )
}

export default function HubStatusCard() {
  const { health, history, loading, error } = useHubStatus()

  if (loading) {
    return <div className="mb-6 h-40 animate-pulse rounded-2xl bg-orange-100/60" />
  }
  if (error) {
    return (
      <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        Failed to load hub status: {error}
      </div>
    )
  }

  const meta = badgeFor(health)

  return (
    <section className="mb-6 rounded-2xl border border-orange-100 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Hub</h2>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${meta.badge}`}>
          {meta.label}
        </span>
      </div>

      {!health ? (
        <p className="text-sm text-stone-500">No hub heartbeats received yet.</p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Last heartbeat" value={timeAgo(Date.parse(health.last_seen))} />
            <Stat label="Pending readings" value={health.pending_count ?? '—'} />
            <Stat label="Uptime" value={fmtUptime(health.uptime_seconds)} />
            <Stat label="WiFi signal" value={health.wifi_rssi != null ? `${health.wifi_rssi} dBm` : '—'} />
          </div>

          {health.last_error && (
            <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              Last error: {health.last_error}
            </div>
          )}

          <div className="mb-1 flex items-baseline justify-between">
            <h3 className="text-xs font-semibold text-stone-600">Activity (pending readings, last 7 d)</h3>
          </div>
          <div className="h-24">
            {history.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={history} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
                  <CartesianGrid stroke="#f0e7dd" vertical={false} />
                  <XAxis
                    dataKey="t"
                    type="number"
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={(t) => fmtTick(t, HISTORY_HOURS)}
                    tick={{ fill: '#8a8580', fontSize: 11 }}
                    stroke="#d9cfc4"
                    minTickGap={40}
                  />
                  <YAxis allowDecimals={false} tick={{ fill: '#8a8580', fontSize: 11 }} stroke="#d9cfc4" />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="pending_count" fill="#ea580c" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-stone-400">
                No heartbeat history in the last 7 days.
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
