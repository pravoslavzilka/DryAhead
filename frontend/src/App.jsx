import { useEffect, useState } from 'react'
import { useSensorData } from './hooks/useSensorData'
import SensorMap from './components/SensorMap'
import SensorCard from './components/SensorCard'
import SensorModal from './components/SensorModal'
import WeatherStrip from './components/WeatherStrip'
import HubStatusCard from './components/HubStatusCard'
import AboutPage from './components/AboutPage'
import { timeAgo } from './lib/format'

export default function App() {
  const { sensors, loading, error, lastUpdated, refresh } = useSensorData()
  const [selected, setSelected] = useState(null)
  const [view, setView] = useState(() => (window.location.hash === '#about' ? 'about' : 'dashboard'))

  const showAbout = () => {
    setView('about')
    history.replaceState(null, '', '#about')
  }
  const showDashboard = () => {
    setView('dashboard')
    history.replaceState(null, '', ' ')
  }

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

  if (view === 'about') {
    return <AboutPage onBack={showDashboard} />
  }

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
            onClick={showAbout}
            className="text-sm font-medium text-stone-500 hover:text-orange-700"
          >
            About
          </button>
          <a
            href="https://github.com/pravoslavzilka/DryAhead"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View on GitHub"
            className="text-stone-500 hover:text-orange-700"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.09 3.29 9.4 7.86 10.93.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.75 2.7 1.25 3.36.96.1-.75.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.18-3.09-.12-.29-.51-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.24 2.76.12 3.05.74.8 1.18 1.83 1.18 3.09 0 4.43-2.7 5.4-5.27 5.69.42.36.78 1.07.78 2.16 0 1.56-.01 2.82-.01 3.2 0 .31.21.67.8.56A10.52 10.52 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
            </svg>
          </a>
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

      <HubStatusCard />

      <footer className="mt-4 text-center text-[11px] text-stone-400">
        Humidity calibrated per sensor: air = 0 %, water = 100 %. Alert fires at the dry-soil limit.
      </footer>

      {selected && <SensorModal sensor={selected} onClose={() => select(null)} />}
    </div>
  )
}
