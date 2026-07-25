import { useEffect, useState } from 'react'

// Zaježová, Slovensko — coordinates of the meteotekov.sk/@zajezova station.
const LAT = 48.453782
const LON = 19.216477
const REFRESH_MS = 15 * 60 * 1000

const WEATHER_URL =
  `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}` +
  `&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,precipitation` +
  `&timezone=auto`

/**
 * Open-Meteo has no direct feed for the meteotekov.sk station itself (no public
 * API, no CORS) — this is the regional forecast model's current estimate for
 * the same coordinates, close but not identical to the station's own reading.
 */
export function useLocalWeather() {
  const [weather, setWeather] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const res = await fetch(WEATHER_URL)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json()
        if (!cancelled) {
          setWeather(json.current)
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(e.message ?? String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const id = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return { weather, loading, error }
}
