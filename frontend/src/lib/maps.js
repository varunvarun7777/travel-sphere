import { stopItems } from './trip'

const TRAVEL_MODE = { walk: 'walking', transit: 'transit', drive: 'driving' }
const MAX_WAYPOINTS = 9

// With "auto", use whichever mode covers most of the day's distance.
function dayTravelMode(day, tripMode) {
  if (TRAVEL_MODE[tripMode]) return TRAVEL_MODE[tripMode]
  const kmByMode = {}
  day.items
    .filter((item) => item.type === 'travel')
    .forEach((leg) => {
      kmByMode[leg.mode] = (kmByMode[leg.mode] || 0) + leg.km
    })
  const [top] = Object.entries(kmByMode).sort((a, b) => b[1] - a[1])
  return TRAVEL_MODE[top?.[0]] || 'walking'
}

/** Google Maps directions for one day: from the base through every stop and back. */
export function googleMapsDayUrl(base, day, tripMode) {
  const points = stopItems(day).map((s) => `${s.place.lat},${s.place.lng}`)
  if (!points.length) return null
  const home = `${base.lat},${base.lng}`
  const tooMany = points.length > MAX_WAYPOINTS
  const params = new URLSearchParams({
    api: '1',
    origin: home,
    destination: tooMany ? points[points.length - 1] : home,
    waypoints: (tooMany ? points.slice(0, MAX_WAYPOINTS) : points).join('|'),
    travelmode: dayTravelMode(day, tripMode),
  })
  return `https://www.google.com/maps/dir/?${params}`
}
