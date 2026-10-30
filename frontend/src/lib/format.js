const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function parseDate(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function toISODate(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function addDays(iso, n) {
  const d = parseDate(iso)
  d.setDate(d.getDate() + n)
  return toISODate(d)
}

export function formatDateRange(startIso, days) {
  const s = parseDate(startIso)
  const e = parseDate(addDays(startIso, Math.max(days, 1) - 1))
  const full = (d) => `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
  if (days <= 1) return full(s)
  if (s.getFullYear() !== e.getFullYear()) return `${full(s)} – ${full(e)}`
  if (s.getMonth() !== e.getMonth()) {
    return `${s.getDate()} ${MONTHS[s.getMonth()]} – ${full(e)}`
  }
  return `${s.getDate()}–${full(e)}`
}

export function formatMinutes(min) {
  const m = Math.round(min || 0)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h} h ${r} min` : `${h} h`
}

export function formatKm(km) {
  const v = km || 0
  if (v < 1) return `${Math.round(v * 100) * 10} m`
  return `${v.toFixed(1)} km`
}

export function formatPrice(price, symbol) {
  if (!price) return 'Free'
  const amount = Number.isInteger(price) ? price.toLocaleString('en') : price.toFixed(2)
  return `${symbol}${amount}`
}

export function humanize(value) {
  if (!value) return ''
  const text = String(value).replace(/[_-]+/g, ' ')
  return text[0].toUpperCase() + text.slice(1)
}

export function hoursLabel(place) {
  if (!place.open || !place.close) return ''
  if (place.open === '00:00' && ['23:59', '24:00'].includes(place.close)) return 'Open all day'
  return `Open ${place.open}–${place.close}`
}

export function closedDaysLabel(days) {
  return days?.length ? `Closed ${days.map((d) => WEEKDAYS[d]).join(', ')}` : ''
}

export const BEST_TIME = {
  morning: 'Best in the morning',
  sunset: 'Best at sunset',
  evening: 'Best in the evening',
}

export function splitDayLabel(label) {
  const [weekday, ...rest] = label.split(' ')
  return { weekday, date: rest.join(' ') }
}

export function slugify(text) {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}
