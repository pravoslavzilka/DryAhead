import { useEffect, useState } from 'react'
import { LAT, LON } from './useLocalWeather'
import { MODEL_INFO } from '../lib/droughtForecast'

const PAST_DAYS = 7 // fills the wetting model's top-layer store before today
const FORECAST_DAYS = 16 // Open-Meteo's maximum
const CACHE_MS = 60 * 60 * 1000

const URL =
  `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}` +
  `&daily=et0_fao_evapotranspiration,precipitation_sum` +
  `&past_days=${PAST_DAYS}&forecast_days=${FORECAST_DAYS}` +
  `&timezone=${encodeURIComponent(MODEL_INFO.timezone)}`

let cache = null // { at, promise } — one request shared by every card and the modal

function load() {
  if (cache && Date.now() - cache.at < CACHE_MS) return cache.promise
  const promise = fetch(URL)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json()
    })
    .then(({ daily }) => {
      // Models were fitted on the station's ET0, which runs below Open-Meteo's;
      // et0_scale puts the forecast on the station's scale.
      const days = daily.time.map((date, i) => ({
        date,
        et0: (daily.et0_fao_evapotranspiration[i] ?? 0) * MODEL_INFO.et0_scale,
        rain: daily.precipitation_sum[i] ?? 0,
      }))
      const today = new Intl.DateTimeFormat('en-CA', { timeZone: MODEL_INFO.timezone }).format(new Date())
      return { days, todayIdx: days.findIndex((d) => d.date === today) }
    })
  promise.catch(() => { cache = null })
  cache = { at: Date.now(), promise }
  return promise
}

/** Daily ET0 + rain for the drought forecast: last 7 days and the next 16. */
export function useDroughtWeather(enabled = true) {
  const [state, setState] = useState({ weather: null, error: null })
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    load()
      .then((weather) => !cancelled && setState({ weather, error: null }))
      .catch((e) => !cancelled && setState({ weather: null, error: e.message ?? String(e) }))
    return () => { cancelled = true }
  }, [enabled])
  return state
}
