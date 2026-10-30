import { useEffect, useState } from 'react'
import { fetchForecast } from '../lib/weather'

/** Daily forecast keyed by date for trip days within the next 15 days. Fails silently to {}. */
export function useWeather(lat, lng, dates) {
  const [weather, setWeather] = useState({})
  const key = dates.join(',')

  useEffect(() => {
    let cancelled = false
    fetchForecast(lat, lng, key.split(',')).then((result) => {
      if (!cancelled) setWeather(result)
    })
    return () => {
      cancelled = true
    }
  }, [lat, lng, key])

  return weather
}
