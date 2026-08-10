import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import { STATUS_META } from '../lib/calibration'
import { timeAgo, fmtPct, fmtTemp } from '../lib/format'

function markerIcon(sensor) {
  const pct = sensor.latest?.humidity
  const label = pct == null ? '?' : `${Math.round(pct)}%`
  const alert = sensor.status === 'critical' ? '<span class="marker-alert">⚠️</span>' : ''
  return L.divIcon({
    className: 'marker-wrap',
    html: `<div style="position:relative"><div class="marker-pin status-${sensor.status}"><span>${label}</span></div>${alert}</div>`,
    iconSize: [46, 46],
    iconAnchor: [23, 44],
    popupAnchor: [0, -44],
  })
}

function FitBounds({ positions }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length === 1) {
      map.setView(positions[0], 14)
    } else if (positions.length > 1) {
      map.fitBounds(L.latLngBounds(positions), { padding: [50, 50] })
    }
  }, [map, positions])
  return null
}

export default function SensorMap({ sensors, onSelect }) {
  const located = sensors.filter((s) => s.gps)
  const positions = located.map((s) => [s.gps.lat, s.gps.lng])

  if (!located.length) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-stone-500">
        No sensors with GPS coordinates yet.
      </div>
    )
  }

  return (
    <MapContainer
      center={positions[0]}
      zoom={13}
      scrollWheelZoom
      className="h-full w-full"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds positions={positions} />
      {located.map((s) => {
        const meta = STATUS_META[s.status]
        return (
          <Marker key={s.nodeId} position={[s.gps.lat, s.gps.lng]} icon={markerIcon(s)}>
            <Popup>
              <div className="min-w-44 space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold">Sensor {s.nodeId}</span>
                  <span className="text-xs font-medium" style={{ color: meta.color }}>
                    {s.status === 'critical' ? '⚠️ ' : ''}{meta.label}
                  </span>
                </div>
                <div className="text-2xl font-bold text-stone-800">
                  {fmtPct(s.latest?.humidity)}
                </div>
                <div className="text-xs text-stone-500">
                  Temperature: {fmtTemp(s.latest?.temperature)}
                  <br />
                  Last reading: {timeAgo(s.latest?.t)}
                </div>
                <button
                  onClick={() => onSelect(s)}
                  className="mt-1 w-full rounded-md bg-orange-600 px-2 py-1 text-xs font-semibold text-white hover:bg-orange-700"
                >
                  View details
                </button>
              </div>
            </Popup>
          </Marker>
        )
      })}
    </MapContainer>
  )
}
