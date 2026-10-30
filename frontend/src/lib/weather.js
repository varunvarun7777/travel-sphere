import { addDays, toISODate } from './format'

const FORECAST_DAYS = 15

export function describeWeather(code) {
  if (code === 0) return 'Clear'
  if (code <= 2) return 'Partly cloudy'
  if (code === 3) return 'Overcast'
  if (code <= 48) return 'Fog'
  if (code <= 57) return 'Drizzle'
  if (code <= 67) return 'Rain'
  if (code <= 77) return 'Snow'
  if (code <= 82) return 'Showers'
  if (code <= 86) return 'Snow showers'
  return 'Thunderstorms'
}

/** Returns { [date]: { code, label, max, min, rain } } for dates inside the forecast window; {} on any failure. */
export async function fetchForecast(lat, lng, dates) {
  const today = toISODate(new Date())
  const limit = addDays(today, FORECAST_DAYS)
  const inRange = dates.filter((d) => d >= today && d < limit).sort()
  if (!inRange.length) return {}

  const params = new URLSearchParams({
    latitude: lat,
    longitude: lng,
    daily: 'weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
    timezone: 'auto',
    start_date: inRange[0],
    end_date: inRange[inRange.length - 1],
  })
  try {
    const res = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`)
    if (!res.ok) return {}
    const { daily } = await res.json()
    const out = {}
    daily.time.forEach((date, i) => {
      const code = daily.weathercode[i]
      out[date] = {
        code,
        label: describeWeather(code),
        max: Math.round(daily.temperature_2m_max[i]),
        min: Math.round(daily.temperature_2m_min[i]),
        rain: daily.precipitation_probability_max[i] ?? 0,
      }
    })
    return out
  } catch {
    return {}
  }
}
