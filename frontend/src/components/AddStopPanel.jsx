import { useMemo, useState } from 'react'
import { api } from '../api'
import { formatKm, formatMinutes, formatPrice, humanize, slugify } from '../lib/format'
import { distanceKm } from '../lib/geo'
import { stopItems } from '../lib/trip'
import { IconClose, IconPlus } from './Icons'
import { btn, fieldLabel, iconBtn, input, panel } from './ui'

const SUGGESTION_COUNT = 8
const DURATIONS = [30, 60, 90, 120]

/** Suggests unused city places nearest to the day's stops, and finds any other place by search. */
export default function AddStopPanel({ trip, dayIndex, cityPlaces, onAdd, onClose, busy }) {
  const [filter, setFilter] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [duration, setDuration] = useState(60)

  const day = trip.days[dayIndex]
  const symbol = trip.city.symbol

  const suggestions = useMemo(() => {
    const used = new Set(trip.days.flatMap((d) => d.stops))
    const avoided = new Set(trip.prefs.avoid || [])
    const anchors = stopItems(day).map((s) => s.place)
    if (!anchors.length) anchors.push(trip.base)
    const q = filter.trim().toLowerCase()
    const ranked = cityPlaces
      .filter((p) => !used.has(p.id) && !avoided.has(p.id))
      .filter((p) => !q || p.name.toLowerCase().includes(q) || p.kind.toLowerCase().includes(q) || p.tags.some((t) => t.includes(q)))
      .map((p) => {
        const nearest = anchors.reduce(
          (best, a) => {
            const km = distanceKm(p, a)
            return km < best.km ? { km, name: a.name } : best
          },
          { km: Infinity, name: '' },
        )
        return { place: p, nearest }
      })
      .sort((a, b) => a.nearest.km - b.nearest.km)
    return q ? ranked.slice(0, 20) : ranked.slice(0, SUGGESTION_COUNT)
  }, [cityPlaces, trip, day, filter])

  async function search() {
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setSearchError('')
    try {
      const found = await api.geocode(q, trip.city.id)
      setResults(found)
      if (!found.length) setSearchError(`No matches for “${q}” in ${trip.city.name}. Try a landmark or street name.`)
    } catch (err) {
      setSearchError(err.message)
    } finally {
      setSearching(false)
    }
  }

  function addCustom(result) {
    onAdd({
      id: `custom:${slugify(result.name) || Date.now()}`,
      name: result.name,
      lat: result.lat,
      lng: result.lng,
      duration,
    })
  }

  return (
    <section className={`${panel} mt-2 p-4`} aria-label={`Add a stop to ${day.label}`}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-display wide text-lg font-extrabold">Add a stop to line {dayIndex + 1}</h3>
        <button type="button" className={iconBtn} onClick={onClose} aria-label="Close add a stop">
          <IconClose />
        </button>
      </div>

      <label className="mt-3 block">
        <span className={fieldLabel}>Nearby and unused</span>
        <input className={`${input} mt-1`} placeholder="Filter by name, kind or tag" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </label>
      {suggestions.length === 0 ? (
        <p className="mt-3 text-sm text-steel">{cityPlaces.length ? 'No unused places match that filter.' : 'Loading city places…'}</p>
      ) : (
        <ul className="mt-2 divide-y divide-rule">
          {suggestions.map(({ place, nearest }) => (
            <li key={place.id} className="flex items-center gap-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{place.name}</p>
                <p className="font-mono text-xs text-steel">
                  {humanize(place.kind)} · {formatMinutes(place.duration)} · {formatPrice(place.price, symbol)} · {formatKm(nearest.km)} from {nearest.name}
                </p>
              </div>
              <button type="button" className={btn} disabled={busy} onClick={() => onAdd(place)}>
                <IconPlus /> Add
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 border-t border-rule pt-4">
        <span className={fieldLabel} id="custom-search-label">
          Not on the list? Search the map
        </span>
        <div className="mt-1 flex gap-2">
          <input
            className={input}
            aria-labelledby="custom-search-label"
            placeholder={`e.g. a café or shop in ${trip.city.name}`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                search()
              }
            }}
          />
          <button type="button" className={btn} onClick={search} disabled={searching || !query.trim()}>
            {searching ? 'Searching…' : 'Search'}
          </button>
        </div>
        <label className="mt-2 flex items-center gap-2 text-sm text-steel">
          Time there
          <select className="rounded-md border border-rule bg-white px-2 py-1 text-sm text-ink" value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
            {DURATIONS.map((d) => (
              <option key={d} value={d}>
                {formatMinutes(d)}
              </option>
            ))}
          </select>
        </label>
        {searchError && <p className="mt-2 text-sm text-[#B3261E]">{searchError}</p>}
        {results?.length > 0 && (
          <ul className="mt-2 divide-y divide-rule">
            {results.map((r) => (
              <li key={`${r.name}-${r.lat}-${r.lng}`} className="flex items-center gap-3 py-2">
                <p className="min-w-0 flex-1 truncate text-sm">{r.name}</p>
                <button type="button" className={btn} disabled={busy} onClick={() => addCustom(r)}>
                  <IconPlus /> Add
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
