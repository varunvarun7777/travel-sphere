import { useCallback, useRef, useState } from 'react'
import { api } from '../api'
import { formatKm } from '../lib/format'
import { MODES } from '../lib/lines'
import { scheduleRequest, stopItems, tripMetrics } from '../lib/trip'

/**
 * Holds a trip and every edit the trip view can make to it.
 * Each edit re-times the affected day(s) via POST /api/schedule, then recomputes trip metrics.
 * A failed request leaves the trip unchanged and reports the error through `notify`.
 */
export function useTripEditor(initialTrip, notify) {
  const [trip, setTrip] = useState(initialTrip)
  const [busyDays, setBusyDays] = useState([])
  const tripRef = useRef(trip)

  const commit = useCallback((next) => {
    tripRef.current = next
    setTrip(next)
  }, [])

  // changes: [{ index, stops, locked? }]; patch: top-level trip fields applied only if re-timing succeeds.
  const retime = useCallback(
    async (changes, { optimize = false, patch = {} } = {}) => {
      const draft = { ...tripRef.current, ...patch }
      setBusyDays(changes.map((c) => c.index))
      try {
        const results = await Promise.all(
          changes.map((c) => {
            const day = draft.days[c.index]
            return api.schedule(scheduleRequest(draft, day, c.stops, c.locked ?? day.locked ?? [], optimize))
          }),
        )
        const days = draft.days.map((day, i) => {
          const k = changes.findIndex((c) => c.index === i)
          return k < 0 ? day : { ...day, ...results[k] }
        })
        commit({ ...draft, days, metrics: tripMetrics(days) })
        return results
      } catch (err) {
        notify(err.message, 'error')
        return null
      } finally {
        setBusyDays([])
      }
    },
    [commit, notify],
  )

  const dayAt = (i) => tripRef.current.days[i]
  const nameOf = (day, id) => stopItems(day).find((s) => s.id === id)?.place.name ?? 'Stop'

  function reorder(i, id, toIndex) {
    const stops = dayAt(i).stops.filter((s) => s !== id)
    stops.splice(Math.max(0, Math.min(toIndex, stops.length)), 0, id)
    return retime([{ index: i, stops }])
  }

  function toggleLock(i, id) {
    const t = tripRef.current
    const day = t.days[i]
    const current = day.locked || []
    const locked = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    commit({ ...t, days: t.days.map((d, k) => (k === i ? { ...d, locked } : d)) })
  }

  async function remove(i, id) {
    const day = dayAt(i)
    const name = nameOf(day, id)
    const unplaced = [...(tripRef.current.unplaced || []).filter((u) => u.id !== id), { id, name, reason: 'Removed by you' }]
    const ok = await retime(
      [{ index: i, stops: day.stops.filter((s) => s !== id), locked: (day.locked || []).filter((s) => s !== id) }],
      { patch: { unplaced } },
    )
    if (ok) notify(`Removed ${name}. It’s in “Didn’t make the cut” if you change your mind.`)
  }

  async function moveToDay(from, id, to) {
    if (from === to) return
    const source = dayAt(from)
    const target = dayAt(to)
    const name = nameOf(source, id)
    const ok = await retime([
      { index: from, stops: source.stops.filter((s) => s !== id), locked: (source.locked || []).filter((s) => s !== id) },
      { index: to, stops: [...target.stops, id] },
    ])
    if (ok) notify(`Moved ${name} to ${target.label}.`)
  }

  async function optimise(i) {
    const results = await retime([{ index: i, stops: dayAt(i).stops }], { optimize: true })
    if (!results) return
    const { naive_km = 0, km = 0 } = results[0].metrics || {}
    const saved = naive_km - km
    notify(saved >= 0.05 ? `Route reordered — ${formatKm(saved)} shorter` : 'Kept this order — it already fits opening hours and timing best.')
  }

  async function setMode(mode) {
    const t = tripRef.current
    if (t.prefs.mode === mode) return
    const ok = await retime(
      t.days.map((d, index) => ({ index, stops: d.stops })),
      { patch: { prefs: { ...t.prefs, mode } } },
    )
    const label = MODES.find((m) => m.id === mode)?.label.toLowerCase()
    if (ok) notify(`Re-timed ${t.days.length === 1 ? 'the day' : `all ${t.days.length} days`} for ${label}.`)
  }

  /** place: a city Place, or a custom place { id: "custom:…", name, lat, lng, duration }. */
  async function addStop(i, place) {
    const t = tripRef.current
    if (t.days.some((d) => d.stops.includes(place.id))) {
      notify(`${place.name} is already in your trip.`)
      return
    }
    const customs = t.custom_places || []
    const isNewCustom = place.id.startsWith('custom:') && !customs.some((c) => c.id === place.id)
    const patch = {
      custom_places: isNewCustom ? [...customs, { id: place.id, name: place.name, lat: place.lat, lng: place.lng, duration: place.duration }] : customs,
      unplaced: (t.unplaced || []).filter((u) => u.id !== place.id),
    }
    const ok = await retime([{ index: i, stops: [...dayAt(i).stops, place.id] }], { patch })
    if (ok) notify(`Added ${place.name} to the end of the day. Optimise route to fit it in the best spot.`)
  }

  function setBrief(brief) {
    commit({ ...tripRef.current, brief })
  }

  return { trip, busyDays, reorder, toggleLock, remove, moveToDay, optimise, setMode, addStop, setBrief }
}
