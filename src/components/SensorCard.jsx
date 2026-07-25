import { ResponsiveContainer, AreaChart, Area, YAxis, ReferenceLine } from 'recharts'
import { STATUS_META } from '../lib/calibration'
import { timeAgo, fmtPct, fmtTemp } from '../lib/format'

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="#d03b3b" aria-label="Drought alert">
      <path d="M12 2 1 21h22L12 2Zm0 6.5c.6 0 1 .4 1 1v5a1 1 0 1 1-2 0v-5c0-.6.4-1 1-1Zm0 8.6a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4Z" />
    </svg>
  )
}

export default function SensorCard({ sensor, onSelect }) {
  const { latest, history, status, dryPct, wetPct } = sensor
  const meta = STATUS_META[status]
  const isAlert = status === 'critical'
  const spark = history.filter((p) => p.humidity != null)
  const values = spark.map((p) => p.humidity)
  const min = values.length ? Math.min(...values) : null
  const max = values.length ? Math.max(...values) : null

  return (
    <button
      onClick={() => onSelect(sensor)}
      className={`group flex flex-col gap-3 rounded-2xl border bg-white p-4 text-left shadow-sm transition
        hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500
        ${isAlert ? 'border-red-300 ring-1 ring-red-200' : 'border-orange-100'}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-stone-800">Sensor {sensor.nodeId}</h3>
          <p className="text-xs text-stone-500">
            {timeAgo(latest?.t)}
            {latest?.temperature != null && ` · ${fmtTemp(latest.temperature)}`}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {isAlert && <AlertIcon />}
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${meta.badge}`}>
            {meta.label}
          </span>
        </div>
      </div>

      <div className="flex items-end justify-between">
        <span className="text-3xl font-bold tracking-tight" style={{ color: meta.color }}>
          {fmtPct(latest?.humidity)}
        </span>
        <span className="text-[11px] text-stone-400">soil humidity</span>
      </div>

      <div className="h-16">
        {spark.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={spark} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`spark-${sensor.nodeId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2a78d6" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#2a78d6" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <YAxis hide domain={[0, 100]} />
              {dryPct != null && (
                <ReferenceLine y={dryPct} stroke="#d03b3b" strokeDasharray="3 3" strokeWidth={1} />
              )}
              <Area
                type="monotone"
                dataKey="humidity"
                stroke="#2a78d6"
                strokeWidth={2}
                fill={`url(#spark-${sensor.nodeId})`}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-stone-400">
            No readings in the last 48 h
          </div>
        )}
      </div>

      <div className="flex justify-between text-[11px] text-stone-500">
        <span>48 h range: {fmtPct(min)} – {fmtPct(max)}</span>
        <span className="font-medium text-orange-600 opacity-0 transition group-hover:opacity-100">
          Details →
        </span>
      </div>
    </button>
  )
}
