import { ResponsiveContainer, AreaChart, Area, YAxis, ReferenceLine } from 'recharts'
import { STATUS_META, MAX_WATER_CONTENT, isAlertStatus } from '../lib/calibration'
import { trendText } from '../lib/droughtStatus'
import { timeAgo, fmtTemp } from '../lib/format'
import { nodeModel, currentRaw, forecastNode } from '../lib/droughtForecast'
import { useDroughtWeather } from '../hooks/useDroughtWeather'

const DAY_MS = 86400000

/** Small label: when this node reaches its estimated stress line if no rain falls. */
function DroughtLabel({ sensor }) {
  const modelled = nodeModel(sensor.nodeId) != null && sensor.status !== 'stale'
  const { weather } = useDroughtWeather(modelled)
  if (nodeModel(sensor.nodeId) == null) {
    return <span className="self-start text-[11px] text-stone-400">No forecast model for this node</span>
  }
  if (!modelled || !weather) return null
  const x0 = currentRaw(sensor.history)
  const f = forecastNode(sensor.nodeId, x0, sensor.latest?.t, weather.days, weather.todayIdx, { withRain: false })
  if (!f) return null

  const horizonDays = weather.days.length - weather.todayIdx
  let text, cls
  if (f.stressedNow) {
    text = 'At or past the estimated stress line'
    cls = 'bg-red-100 text-red-700 border-red-200'
  } else if (f.stressAt != null) {
    const days = Math.max(1, Math.round((f.stressAt - Date.now()) / DAY_MS))
    const date = new Date(f.stressAt).toLocaleDateString([], { day: 'numeric', month: 'short' })
    text = `Estimated stress in ~${days} d (${date}) if no rain`
    cls = days <= 3 ? 'bg-red-100 text-red-700 border-red-200'
      : days <= 7 ? 'bg-orange-100 text-orange-700 border-orange-200'
        : 'bg-amber-50 text-amber-700 border-amber-200'
  } else {
    text = `Stress line not reached within ${horizonDays} d without rain (estimate)`
    cls = 'bg-stone-50 text-stone-500 border-stone-200'
  }
  return (
    <span
      className={`self-start rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}
      title="Rough estimate: this node's fitted drying model driven by the Open-Meteo 16-day forecast, assuming no rain. The stress line comes from the model and has not been checked against plants."
    >
      {text}
    </span>
  )
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="#d03b3b" aria-label="Drought alert">
      <path d="M12 2 1 21h22L12 2Zm0 6.5c.6 0 1 .4 1 1v5a1 1 0 1 1-2 0v-5c0-.6.4-1 1-1Zm0 8.6a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4Z" />
    </svg>
  )
}

export default function SensorCard({ sensor, onSelect }) {
  const { latest, history, status, trend, limitPct } = sensor
  const meta = STATUS_META[status]
  const isAlert = isAlertStatus(status)
  const spark = history.filter((p) => p.waterContent != null)

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
        {isAlert && <AlertIcon />}
      </div>

      <div>
        <div className="text-2xl font-bold tracking-tight" style={{ color: meta.color }}>
          {meta.label}
        </div>
        <div className="text-xs text-stone-500">
          {status === 'stale' ? 'Waiting for new readings' : trendText(trend)}
        </div>
      </div>

      <DroughtLabel sensor={sensor} />

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
              <YAxis hide domain={[0, MAX_WATER_CONTENT]} />
              {limitPct != null && (
                <ReferenceLine y={limitPct} stroke="#d03b3b" strokeDasharray="3 3" strokeWidth={1} />
              )}
              <Area
                type="monotone"
                dataKey="waterContent"
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
        <span>Last 48 h</span>
        <span className="font-medium text-orange-600 opacity-0 transition group-hover:opacity-100">
          Details →
        </span>
      </div>
    </button>
  )
}
