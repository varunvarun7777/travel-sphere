import { readJSON, session, writeJSON } from './storage'

const DRAFT_KEY = 'travelsphere.draft'

export const readDraft = () => readJSON(session, DRAFT_KEY)
export const writeDraft = (draft) => writeJSON(session, DRAFT_KEY, draft)
export const clearDraft = () => session.remove(DRAFT_KEY)

export const stopItems = (day) => day.items.filter((item) => item.type === 'stop')

export function defaultTitle(trip) {
  const n = trip.days.length
  return `${n} ${n === 1 ? 'day' : 'days'} in ${trip.city.name}`
}

export function hasNatureStops(day) {
  return stopItems(day).some((s) => s.place.tags?.includes('nature') || s.place.kind === 'park')
}

const round1 = (n) => Math.round(n * 10) / 10

export function tripMetrics(days) {
  const sum = (key) => days.reduce((total, day) => total + (day.metrics?.[key] || 0), 0)
  const km = sum('km')
  const naive = sum('naive_km')
  return {
    stops: sum('stops'),
    km: round1(km),
    walk_km: round1(sum('walk_km')),
    travel_min: Math.round(sum('travel_min')),
    fees: round1(sum('fees')),
    naive_km: round1(naive),
    saved_pct: naive > 0 ? Math.max(0, Math.round(((naive - km) / naive) * 100)) : 0,
  }
}

export function scheduleRequest(trip, day, stops, locked, optimize) {
  return {
    city: trip.city.id,
    date: day.date,
    pace: trip.prefs.pace,
    mode: trip.prefs.mode,
    base: trip.base,
    start: day.start,
    end: day.end,
    stops,
    locked: locked.filter((id) => stops.includes(id)),
    custom_places: trip.custom_places || [],
    optimize,
  }
}
