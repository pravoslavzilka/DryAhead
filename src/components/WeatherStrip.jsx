import { useLocalWeather } from '../hooks/useLocalWeather'
import { describeWeatherCode } from '../lib/weatherCodes'

export default function WeatherStrip() {
  const { weather, loading, error } = useLocalWeather()

  if (loading || error || !weather) return null

  const [label, icon] = describeWeatherCode(weather.weather_code)

  return (
    <div className="mt-8 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-orange-100 bg-white px-4 py-3 text-sm text-stone-600 shadow-sm">
      <div className="flex items-center gap-3">
        <span className="text-xl" aria-hidden="true">{icon}</span>
        <span>
          <span className="font-semibold text-stone-800">Zaježová</span>{' '}
          {weather.temperature_2m.toFixed(1)} °C · {label} · {weather.relative_humidity_2m}% humidity ·{' '}
          {weather.wind_speed_10m.toFixed(0)} km/h wind · {weather.precipitation.toFixed(1)} mm precipitation
        </span>
      </div>
      <a
        href="https://meteotekov.sk/@zajezova"
        target="_blank"
        rel="noreferrer"
        className="text-xs text-orange-600 hover:underline"
      >
        Regional estimate — live station reading →
      </a>
    </div>
  )
}
