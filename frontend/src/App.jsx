import { useEffect, useState } from 'react'
import { useSensorData } from './hooks/useSensorData'
import SensorMap from './components/SensorMap'
import SensorCard from './components/SensorCard'
import SensorModal from './components/SensorModal'
import WeatherStrip from './components/WeatherStrip'
import { timeAgo } from './lib/format'

export default function App() {
  const { sensors, loading, error, lastUpdated, refresh } = useSensorData()
  const [selected, setSelected] = useState(null)

  // Deep link: #sensor-3 opens that sensor's detail modal once data is in.
  useEffect(() => {
    const m = window.location.hash.match(/^#sensor-(\d+)$/)
    if (!m) return
    const s = sensors.find((x) => x.nodeId === Number(m[1]))
    if (s) setSelected(s)
  }, [sensors])

  const select = (s) => {
    setSelected(s)
    history.replaceState(null, '', s ? `#sensor-${s.nodeId}` : ' ')
  }

  const alerts = sensors.filter((s) => s.status === 'critical')

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      {/* Header */}
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-stone-800">
            DryAhead
          </h1>
          <p className="text-sm text-stone-500">
            Live soil-humidity network · updates every 20 min
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-stone-400">
            {lastUpdated ? `Refreshed ${timeAgo(lastUpdated)}` : ''}
          </span>
          <button
            onClick={refresh}
            className="rounded-full border border-orange-200 bg-white px-4 py-1.5 text-sm font-semibold text-orange-700 shadow-sm transition hover:bg-orange-50"
          >
            ↻ Refresh
          </button>
        </div>
      </header>

      {/* Alert banner */}
      {alerts.length > 0 && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          <span className="text-base">⚠️</span>
          Drought alert: {alerts.map((s) => `Sensor ${s.nodeId}`).join(', ')}{' '}
          {alerts.length === 1 ? 'is' : 'are'} below the dry-soil limit.
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Failed to load data: {error}
        </div>
      )}

      {/* Map */}
      <section className="mb-6 overflow-hidden rounded-2xl border border-orange-100 bg-white shadow-sm">
        <div className="h-[420px]">
          {loading ? (
            <div className="flex h-full items-center justify-center text-sm text-stone-400">
              Loading sensors…
            </div>
          ) : (
            <SensorMap sensors={sensors} onSelect={select} />
          )}
        </div>
      </section>

      {/* Sensor cards */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-stone-500">
          Sensors ({sensors.length})
        </h2>
        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-48 animate-pulse rounded-2xl bg-orange-100/60" />
            ))}
          </div>
        ) : sensors.length === 0 ? (
          <p className="text-sm text-stone-500">
            No sensors found in <code>sensor_calibration</code>.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sensors.map((s) => (
              <SensorCard key={s.nodeId} sensor={s} onSelect={select} />
            ))}
          </div>
        )}
      </section>

      <WeatherStrip />

      <footer className="mt-4 text-center text-[11px] text-stone-400">
        Humidity calibrated per sensor: air = 0 %, water = 100 %. Alert fires at the dry-soil limit.
      </footer>

      {selected && <SensorModal sensor={selected} onClose={() => select(null)} />}
    </div>
  )
}
