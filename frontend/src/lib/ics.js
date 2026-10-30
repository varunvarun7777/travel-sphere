import { formatPrice, hoursLabel, slugify } from './format'
import { stopItems } from './trip'

const escapeText = (text) =>
  String(text).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n')

// Floating local time: the event happens at this wall-clock time wherever the city is.
const localStamp = (date, time) => `${date.replace(/-/g, '')}T${time.replace(':', '')}00`

// RFC 5545 asks for lines of at most 75 octets; continuation lines start with a space.
function fold(line) {
  const parts = []
  let rest = line
  while (rest.length > 74) {
    parts.push(rest.slice(0, 74))
    rest = rest.slice(74)
  }
  parts.push(rest)
  return parts.join('\r\n ')
}

export function buildIcs(trip) {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//TravelSphere//Itinerary//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH']

  trip.days.forEach((day, dayIndex) => {
    stopItems(day).forEach((stop, stopIndex) => {
      const p = stop.place
      const details = [p.blurb, hoursLabel(p), `Entry: ${formatPrice(p.price, trip.city.symbol)}`, `Line ${dayIndex + 1}, stop ${stopIndex + 1}`]
      lines.push(
        'BEGIN:VEVENT',
        `UID:${day.date}-${slugify(stop.id)}-${stopIndex}@travelsphere.app`,
        `DTSTAMP:${stamp}`,
        `DTSTART:${localStamp(day.date, stop.start)}`,
        `DTEND:${localStamp(day.date, stop.end)}`,
        `SUMMARY:${escapeText(p.name)}`,
        `LOCATION:${escapeText(`${p.name}, ${trip.city.name}`)}`,
        `GEO:${p.lat};${p.lng}`,
        `DESCRIPTION:${escapeText(details.filter(Boolean).join('\n'))}`,
        'END:VEVENT',
      )
    })
  })

  lines.push('END:VCALENDAR')
  return lines.map(fold).join('\r\n')
}

export function downloadIcs(trip, filename) {
  const blob = new Blob([buildIcs(trip)], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
