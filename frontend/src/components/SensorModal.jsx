import { useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, LineChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, Brush,
} from 'recharts'
import { fetchNodeHistory } from '../hooks/useSensorData'
import { STATUS_META, READINGS_PER_DAY, rawToHumidity } from '../lib/calibration'
import { timeAgo, fmtDateTime, fmtTick, fmtPct, fmtTemp } from '../lib/format'
import { nodeModel, currentRaw, forecastNode, stressPct, MODEL_INFO } from '../lib/droughtForecast'
import { useDroughtWeather } from '../hooks/useDroughtWeather'

const DAY_MS = 86400000
const FC_DRY_COLOR = '#ea580c'
const FC_RAIN_COLOR = '#0d9488'
const STRESS_COLOR = '#9333ea'

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
      {p.fcDry != null && (
        <div className="text-stone-600">
          Forecast, no rain: <span className="font-semibold" style={{ color: FC_DRY_COLOR }}>{fmtPct(p.fcDry, 1)}</span>
        </div>
      )}
      {p.fcRain != null && (
        <div className="text-stone-600">
          Forecast, with rain: <span className="font-semibold" style={{ color: FC_RAIN_COLOR }}>{fmtPct(p.fcRain, 1)}</span>
          {p.rainMm > 0 && <span className="text-stone-400"> ({p.rainMm.toFixed(1)} mm that day)</span>}
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

// Green -> yellow -> orange -> red, by share of the day's expected readings present.
const COMPLETENESS_LEVELS = [
  { min: 0.9, color: '#0ca30c', label: 'Complete' },
  { min: 0.6, color: '#fab219', label: 'Partial' },
  { min: 0.3, color: '#ec835a', label: 'Sparse' },
  { min: 0, color: '#d03b3b', label: 'Minimal' },
]
const NO_DATA_LEVEL = { color: '#a8a29e', label: 'No data' }

function completenessLevel(count, ratio) {
  if (count === 0) return NO_DATA_LEVEL
  return COMPLETENESS_LEVELS.find((l) => ratio >= l.min)
}

function startOfDay(ms) {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** One entry per calendar day covered by the loaded range, with a read count and
 * completeness ratio against the expected reading cadence (partial for the range's
 * first/last day, whose coverage may be less than a full 24 h). */
function buildDayCompleteness(data, rangeStart, now) {
  const DAY_MS = 86400000

  const counts = new Map()
  for (const p of data) {
    const day = startOfDay(p.t)
    counts.set(day, (counts.get(day) ?? 0) + 1)
  }

  const days = []
  for (let d = startOfDay(rangeStart); d <= startOfDay(now); d += DAY_MS) {
    const coverageMs = Math.max(0, Math.min(d + DAY_MS, now) - Math.max(d, rangeStart))
    const expected = (coverageMs / DAY_MS) * READINGS_PER_DAY
    const count = counts.get(d) ?? 0
    days.push({ date: d, count, ratio: expected > 0 ? Math.min(1, count / expected) : 0 })
  }
  return days
}

function CompletenessCalendar({ data, from, to }) {
  const days = buildDayCompleteness(data, from, to)
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-stone-700">Data completeness</h3>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-stone-500">
          {[...COMPLETENESS_LEVELS, NO_DATA_LEVEL].map((l) => (
            <span key={l.label} className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />
              {l.label}
            </span>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {days.map(({ date, count, ratio }) => {
          const level = completenessLevel(count, ratio)
          const dateLabel = new Date(date).toLocaleDateString([], {
            weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
          })
          return (
            <div
              key={date}
              title={`${dateLabel} — ${count} reading${count === 1 ? '' : 's'} (${level.label})`}
              className="h-3.5 w-3.5 rounded-sm"
              style={{ background: level.color }}
            />
          )
        })}
      </div>
    </div>
  )
}

function whenText(f) {
  if (!f) return '—'
  if (f.stressedNow) return 'already in plant stress'
  if (f.stressAt == null) return 'not within the forecast'
  const days = Math.max(1, Math.round((f.stressAt - Date.now()) / DAY_MS))
  return `${new Date(f.stressAt).toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })} (in ~${days} d)`
}

/** Plant-stress dates under both scenarios, plus what the forecast rests on. */
function ForecastSummary({ forecast, cal }) {
  const m = forecast.model
  const errPct = m.validation_rmse_7d_counts != null && cal.air != null && cal.water != null
    ? (m.validation_rmse_7d_counts / Math.abs(cal.air - cal.water)) * 100
    : null
  return (
    <div className="space-y-1 rounded-xl border border-purple-100 bg-purple-50/40 px-4 py-3 text-xs text-stone-600">
      <div>
        <span className="font-semibold" style={{ color: FC_DRY_COLOR }}>If no rain:</span>{' '}
        plant stress {whenText(forecast.dry)}
      </div>
      {forecast.wet ? (
        <div>
          <span className="font-semibold" style={{ color: FC_RAIN_COLOR }}>With forecast rain</span>
          {' '}({forecast.rainTotal.toFixed(1)} mm over {forecast.days} d): plant stress {whenText(forecast.wet)}
        </div>
      ) : (
        <div className="text-stone-500">
          No rain line for this node: its readings don't follow the station's rain, so rain can't be forecast into it.
        </div>
      )}
      <div className="text-[11px] text-stone-400">
        Plant stress ({fmtPct(forecast.stress, 1)}) = soil dry enough that plants struggle to take up water.
        Fitted on this node's own readings {MODEL_INFO.fitted_on.replace('..', ' to ')}; weather from the Open-Meteo
        {' '}{forecast.days}-day forecast.{errPct != null && ` Typical 7-day error ~${errPct.toFixed(1)} %.`}
      </div>
    </div>
  )
}

export default function SensorModal({ sensor, onClose }) {
  const [rangeHours, setRangeHours] = useState(72)
  const [data, setData] = useState(null)
  // The exact window the data was loaded for; the x-axis spans it even where
  // readings are missing, so "7 d" always shows 7 days ending now.
  const [span, setSpan] = useState(null)
  // Brush (zoom slider) selection as data indices, or null when not zoomed.
  const [zoom, setZoom] = useState(null)
  const [error, setError] = useState(null)
  const [showForecast, setShowForecast] = useState(false)
  const hasModel = nodeModel(sensor.nodeId) != null
  const { weather, error: forecastError } = useDroughtWeather(showForecast && hasModel)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    const to = Date.now()
    const from = to - rangeHours * 3600 * 1000
    setData(null)
    setZoom(null)
    setError(null)
    fetchNodeHistory(sensor.nodeId, from, to, sensor.cal)
      .then((rows) => {
        if (cancelled) return
        setSpan({ from, to })
        setData(rows)
      })
      .catch((e) => !cancelled && setError(e.message ?? String(e)))
    return () => { cancelled = true }
  }, [sensor, rangeHours])

  // Drought forecast from the latest readings: no-rain line always, with-rain
  // line only where this node has a rain model.
  const forecast = useMemo(() => {
    if (!showForecast || !weather) return null
    const model = nodeModel(sensor.nodeId)
    const x0 = currentRaw(sensor.history)
    const t0 = sensor.latest?.t
    const run = (withRain) => forecastNode(sensor.nodeId, x0, t0, weather.days, weather.todayIdx, { withRain })
    const dry = run(false)
    if (!model || !dry) return null
    const wet = model.wetting.model !== 'none' ? run(true) : null
    const ahead = weather.days.slice(weather.todayIdx)
    const pct = (raw) => rawToHumidity(raw, sensor.cal)
    const points = dry.points.map((p, i) => ({
      t: p.t,
      fcDry: pct(p.raw),
      fcRain: wet ? pct(wet.points[i].raw) : undefined,
      rainMm: i > 0 ? ahead[i - 1]?.rain : undefined,
    }))
    return {
      model, dry, wet, points,
      stress: stressPct(sensor.nodeId, sensor.cal),
      days: ahead.length,
      rainTotal: ahead.reduce((a, d) => a + d.rain, 0),
      end: points.at(-1).t,
    }
  }, [showForecast, weather, sensor])

  // Observed readings, then forecast points after them (both keyed on t).
  const chartData = data && forecast ? [...data, ...forecast.points] : data

  // Fixed to the selected window (extended to the forecast's end when shown);
  // follows the Brush while zoomed in.
  const xDomain = zoom && chartData?.length
    ? [chartData[zoom.startIndex].t, chartData[zoom.endIndex].t]
    : span ? [span.from, forecast ? Math.max(span.to, forecast.end) : span.to] : ['dataMin', 'dataMax']
  const onBrushChange = ({ startIndex, endIndex }) =>
    setZoom(startIndex === 0 && endIndex === (chartData?.length ?? 0) - 1 ? null : { startIndex, endIndex })

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
            {hasModel && (
              <button
                onClick={() => { setShowForecast((v) => !v); setZoom(null) }}
                className={`ml-auto rounded-full border px-3 py-1 text-xs font-semibold transition ${
                  showForecast
                    ? 'border-purple-600 bg-purple-600 text-white shadow-sm'
                    : 'border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100'
                }`}
              >
                {showForecast ? 'Hide drought forecast' : 'Show drought forecast'}
              </button>
            )}
          </div>

          {showForecast && (
            forecastError ? (
              <div className="text-xs text-red-600">Forecast unavailable: {forecastError}</div>
            ) : !weather ? (
              <div className="text-xs text-stone-400">Loading forecast…</div>
            ) : forecast ? (
              <ForecastSummary forecast={forecast} cal={sensor.cal} />
            ) : (
              <div className="text-xs text-stone-500">Not enough recent readings to start a forecast from.</div>
            )
          )}

          {/* Humidity chart */}
          <div>
            <div className="mb-1 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-stone-700">Soil humidity</h3>
              <span className="text-[11px] text-stone-400">
                <span style={{ color: '#d03b3b' }}>▪</span> dry-soil limit&nbsp;&nbsp;
                <span style={{ color: '#199e70' }}>▪</span> wet-soil limit (mud)
                {forecast && (
                  <>
                    &nbsp;&nbsp;<span style={{ color: STRESS_COLOR }}>▪</span> plant stress
                    &nbsp;&nbsp;<span style={{ color: FC_DRY_COLOR }}>- -</span> forecast, no rain
                    {forecast.wet && <>&nbsp;&nbsp;<span style={{ color: FC_RAIN_COLOR }}>···</span> with rain</>}
                  </>
                )}
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
                  <ComposedChart
                    key={forecast ? 'forecast' : 'observed'}
                    data={chartData}
                    margin={{ top: 8, right: 12, bottom: 0, left: -12 }}
                  >
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
                      domain={xDomain}
                      allowDataOverflow
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
                    {forecast && forecast.stress != null && (
                      <ReferenceLine
                        y={forecast.stress}
                        stroke={STRESS_COLOR}
                        strokeDasharray="4 4"
                        strokeWidth={1.5}
                        label={{ value: 'Plant stress', position: 'insideTopLeft', fill: STRESS_COLOR, fontSize: 11 }}
                      />
                    )}
                    {forecast && (
                      <ReferenceLine
                        x={forecast.points[0].t}
                        stroke="#a8a29e"
                        strokeDasharray="2 3"
                        label={{ value: 'now', position: 'insideTopRight', fill: '#8a8580', fontSize: 11 }}
                      />
                    )}
                    {forecast && (
                      <Line
                        type="monotone"
                        dataKey="fcDry"
                        stroke={FC_DRY_COLOR}
                        strokeWidth={2}
                        strokeDasharray="6 4"
                        dot={false}
                        activeDot={{ r: 4, fill: FC_DRY_COLOR, stroke: '#fff', strokeWidth: 2 }}
                        isAnimationActive={false}
                      />
                    )}
                    {forecast?.wet && (
                      <Line
                        type="monotone"
                        dataKey="fcRain"
                        stroke={FC_RAIN_COLOR}
                        strokeWidth={2}
                        strokeDasharray="2 3"
                        dot={false}
                        activeDot={{ r: 4, fill: FC_RAIN_COLOR, stroke: '#fff', strokeWidth: 2 }}
                        isAnimationActive={false}
                      />
                    )}
                    <Brush
                      dataKey="t"
                      height={26}
                      travellerWidth={8}
                      stroke="#ea580c"
                      fill="#fff7ed"
                      tickFormatter={(t) => fmtTick(t, rangeHours)}
                      onChange={onBrushChange}
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
                      domain={xDomain}
                      allowDataOverflow
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

          {/* Data completeness calendar */}
          {data != null && span && <CompletenessCalendar data={data} from={span.from} to={span.to} />}

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
