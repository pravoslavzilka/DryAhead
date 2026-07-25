import { useEffect, useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, LineChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, Brush,
} from 'recharts'
import { fetchNodeHistory } from '../hooks/useSensorData'
import { STATUS_META } from '../lib/calibration'
import { timeAgo, fmtDateTime, fmtTick, fmtPct, fmtTemp } from '../lib/format'

const RANGES = [
  { label: '24 h', hours: 24 },
  { label: '3 d', hours: 72 },
  { label: '7 d', hours: 168 },
  { label: '30 d', hours: 720 },
  { label: '90 d', hours: 2160 },
]

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-lg border border-orange-100 bg-white/95 px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-semibold text-stone-700">{fmtDateTime(label)}</div>
      {p.humidity != null && (
        <div className="text-stone-600">
          Humidity: <span className="font-semibold" style={{ color: '#1c5cab' }}>{fmtPct(p.humidity, 1)}</span>
          <span className="text-stone-400"> (raw {p.raw})</span>
        </div>
      )}
      {p.temperature != null && (
        <div className="text-stone-600">
          Temperature: <span className="font-semibold" style={{ color: '#c2410c' }}>{fmtTemp(p.temperature)}</span>
        </div>
      )}
      {p.rssi != null && (
        <div className="text-stone-400">RSSI {p.rssi} dBm{p.snr != null ? ` · SNR ${p.snr}` : ''}</div>
      )}
    </div>
  )
}

function Stat({ label, value, color }) {
  return (
    <div className="rounded-xl bg-orange-50/70 px-3 py-2">
      <div className="text-[11px] text-stone-500">{label}</div>
      <div className="text-lg font-bold" style={color ? { color } : undefined}>{value}</div>
    </div>
  )
}

export default function SensorModal({ sensor, onClose }) {
  const [rangeHours, setRangeHours] = useState(72)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    fetchNodeHistory(sensor.nodeId, rangeHours, sensor.cal)
      .then((rows) => !cancelled && setData(rows))
      .catch((e) => !cancelled && setError(e.message ?? String(e)))
    return () => { cancelled = true }
  }, [sensor, rangeHours])

  const { dryPct, wetPct, latest, status } = sensor
  const meta = STATUS_META[status]
  const humidityVals = (data ?? []).map((p) => p.humidity).filter((v) => v != null)
  const avg = humidityVals.length
    ? humidityVals.reduce((a, b) => a + b, 0) / humidityVals.length
    : null

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-stone-900/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-y-auto rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Sensor ${sensor.nodeId} details`}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-orange-100 bg-gradient-to-r from-red-50 to-orange-50 px-6 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-stone-800">Sensor {sensor.nodeId}</h2>
              <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${meta.badge}`}>
                {status === 'critical' ? '⚠️ ' : ''}{meta.label}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-stone-500">
              {sensor.cal.GPS ?? 'No GPS'} · last reading {timeAgo(latest?.t)}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1.5 text-stone-500 hover:bg-orange-100 hover:text-stone-800"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="space-y-5 px-6 py-5">
          {/* Stats */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Current humidity" value={fmtPct(latest?.humidity, 1)} color={meta.color} />
            <Stat label="Temperature" value={fmtTemp(latest?.temperature)} />
            <Stat label={`Average (${RANGES.find((r) => r.hours === rangeHours)?.label})`} value={fmtPct(avg, 1)} />
            <Stat label="Readings loaded" value={data?.length ?? '…'} />
          </div>

          {/* Range selector */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs font-medium text-stone-500">Range:</span>
            {RANGES.map((r) => (
              <button
                key={r.hours}
                onClick={() => setRangeHours(r.hours)}
                className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                  r.hours === rangeHours
                    ? 'bg-orange-600 text-white shadow-sm'
                    : 'bg-orange-50 text-stone-600 hover:bg-orange-100'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          {/* Humidity chart */}
          <div>
            <div className="mb-1 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-stone-700">Soil humidity</h3>
              <span className="text-[11px] text-stone-400">
                <span style={{ color: '#d03b3b' }}>▪</span> dry-soil limit&nbsp;&nbsp;
                <span style={{ color: '#199e70' }}>▪</span> wet-soil limit (mud)
              </span>
            </div>
            <div className="h-80">
              {error ? (
                <div className="flex h-full items-center justify-center text-sm text-red-600">{error}</div>
              ) : data == null ? (
                <div className="flex h-full items-center justify-center text-sm text-stone-400">Loading…</div>
              ) : data.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-stone-400">
                  No readings in this range.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                    <defs>
                      <linearGradient id="hum-grad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#2a78d6" stopOpacity={0.25} />
                        <stop offset="100%" stopColor="#2a78d6" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#f0e7dd" vertical={false} />
                    <XAxis
                      dataKey="t"
                      type="number"
                      domain={['dataMin', 'dataMax']}
                      tickFormatter={(t) => fmtTick(t, rangeHours)}
                      tick={{ fill: '#8a8580', fontSize: 11 }}
                      stroke="#d9cfc4"
                      minTickGap={40}
                    />
                    <YAxis
                      domain={[0, 100]}
                      unit="%"
                      tick={{ fill: '#8a8580', fontSize: 11 }}
                      stroke="#d9cfc4"
                    />
                    <Tooltip content={<ChartTooltip />} />
                    {dryPct != null && (
                      <ReferenceLine
                        y={dryPct}
                        stroke="#d03b3b"
                        strokeDasharray="5 4"
                        strokeWidth={1.5}
                        label={{ value: 'Dry soil', position: 'insideTopRight', fill: '#d03b3b', fontSize: 11 }}
                      />
                    )}
                    {wetPct != null && (
                      <ReferenceLine
                        y={wetPct}
                        stroke="#199e70"
                        strokeDasharray="5 4"
                        strokeWidth={1.5}
                        label={{ value: 'Wet soil (mud)', position: 'insideBottomRight', fill: '#199e70', fontSize: 11 }}
                      />
                    )}
                    <Area
                      type="monotone"
                      dataKey="humidity"
                      stroke="#2a78d6"
                      strokeWidth={2}
                      fill="url(#hum-grad)"
                      dot={false}
                      activeDot={{ r: 4, fill: '#2a78d6', stroke: '#fff', strokeWidth: 2 }}
                      connectNulls
                      isAnimationActive={false}
                    />
                    <Brush
                      dataKey="t"
                      height={26}
                      travellerWidth={8}
                      stroke="#ea580c"
                      fill="#fff7ed"
                      tickFormatter={(t) => fmtTick(t, rangeHours)}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Temperature chart (own axis — never dual-axis) */}
          {data != null && data.some((p) => p.temperature != null) && (
            <div>
              <h3 className="mb-1 text-sm font-semibold text-stone-700">Temperature</h3>
              <div className="h-36">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                    <CartesianGrid stroke="#f0e7dd" vertical={false} />
                    <XAxis
                      dataKey="t"
                      type="number"
                      domain={['dataMin', 'dataMax']}
                      tickFormatter={(t) => fmtTick(t, rangeHours)}
                      tick={{ fill: '#8a8580', fontSize: 11 }}
                      stroke="#d9cfc4"
                      minTickGap={40}
                    />
                    <YAxis
                      unit="°"
                      domain={['auto', 'auto']}
                      tick={{ fill: '#8a8580', fontSize: 11 }}
                      stroke="#d9cfc4"
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="temperature"
                      stroke="#c2410c"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, fill: '#c2410c', stroke: '#fff', strokeWidth: 2 }}
                      connectNulls
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Calibration footer */}
          <div className="rounded-xl border border-orange-100 bg-orange-50/50 px-4 py-3 text-xs text-stone-500">
            <span className="font-semibold text-stone-600">Calibration:</span>{' '}
            air {sensor.cal.air ?? '—'} (0 %) · water {sensor.cal.water ?? '—'} (100 %) ·
            dry soil {sensor.cal.dry_soil ?? '—'} ({fmtPct(dryPct, 1)}) ·
            wet soil {sensor.cal.wet_soil ?? '—'} ({fmtPct(wetPct, 1)})
            {latest?.rssi != null && <> · RSSI {latest.rssi} dBm{latest.snr != null ? ` · SNR ${latest.snr}` : ''}</>}
          </div>
        </div>
      </div>
    </div>
  )
}
