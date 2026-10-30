import { useEffect, useRef } from 'react'
import { MapContainer, Marker, Polyline, Popup, useMap } from 'react-leaflet'
import { BEST_TIME, closedDaysLabel, formatMinutes, formatPrice, hoursLabel, humanize } from '../lib/format'
import { prefersReducedMotion } from '../lib/geo'
import { lineColor } from '../lib/lines'
import { stopItems } from '../lib/trip'
import { AutoResize, BaseTiles, FitBounds, baseIcon, stationIcon } from './mapParts'

function legSegments(day, base) {
  const coords = { base: [base.lat, base.lng] }
  stopItems(day).forEach((s) => {
    coords[s.id] = [s.place.lat, s.place.lng]
  })
  return day.items
    .filter((it) => it.type === 'travel' && coords[it.from] && coords[it.to])
    .map((leg) => ({ mode: leg.mode, positions: [coords[leg.from], coords[leg.to]] }))
}

function PlacePopup({ stop, number, dayLabel, symbol }) {
  const p = stop.place
  const facts = [hoursLabel(p), closedDaysLabel(p.closed_days), `Entry ${formatPrice(p.price, symbol)}`, BEST_TIME[p.best]].filter(Boolean)
  return (
    <div className="w-60">
      <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-steel">
        {dayLabel} · stop {number} · {stop.start}–{stop.end}
      </p>
      <p className="mt-0.5 font-display wide text-base font-extrabold leading-tight text-ink">{p.name}</p>
      <p className="font-mono text-xs text-steel">
        {humanize(p.kind)} · {formatMinutes(p.duration)}
      </p>
      {p.blurb && <p className="mt-1.5 text-[13px] text-ink">{p.blurb}</p>}
      <ul className="mt-1.5 space-y-0.5 text-xs text-steel">
        {facts.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
    </div>
  )
}

function FocusController({ focus, markerRefs }) {
  const map = useMap()
  useEffect(() => {
    if (!focus || focus.source !== 'list') return
    const marker = markerRefs.current[focus.id]
    if (!marker) return
    map.setView(marker.getLatLng(), Math.max(map.getZoom(), 15), { animate: !prefersReducedMotion() })
    marker.openPopup()
  }, [focus, map, markerRefs])
  return null
}

/** Day lines on the map: walk legs dotted, transit and drive solid; numbered roundels per stop. */
export default function TripMap({ trip, selected, allDays, focus, onSelectStop }) {
  const markerRefs = useRef({})
  const symbol = trip.city.symbol

  // Selected day is drawn last so it sits on top of faded lines.
  const visible = trip.days
    .map((day, index) => ({ day, index }))
    .filter(({ index }) => allDays || index === selected)
    .sort((a, b) => (a.index === selected) - (b.index === selected))

  const points = [
    [trip.base.lat, trip.base.lng],
    ...visible.flatMap(({ day }) => stopItems(day).map((s) => [s.place.lat, s.place.lng])),
  ]
  const fitKey = `${selected}|${allDays}|${visible.map(({ day }) => [...day.stops].sort().join(',')).join(';')}`

  return (
    <MapContainer center={[trip.base.lat, trip.base.lng]} zoom={13} scrollWheelZoom fadeAnimation={false} className="h-full w-full">
      <BaseTiles />
      <AutoResize />
      <FitBounds points={points} fitKey={fitKey} />
      <FocusController focus={focus} markerRefs={markerRefs} />

      {visible.map(({ day, index }) => {
        const color = lineColor(index)
        const faded = index !== selected
        return legSegments(day, trip.base).map((seg, i) => (
          <Polyline
            key={`${day.date}-${i}-${seg.mode}`}
            positions={seg.positions}
            pathOptions={{
              color,
              weight: seg.mode === 'walk' ? 5 : 6,
              opacity: faded ? 0.3 : 0.95,
              dashArray: seg.mode === 'walk' ? '0.1 10' : null,
              lineCap: 'round',
            }}
          />
        ))
      })}

      {visible.map(({ day, index }) =>
        stopItems(day).map((stop, i) => (
          <Marker
            key={`${index}-${stop.id}`}
            position={[stop.place.lat, stop.place.lng]}
            icon={stationIcon(lineColor(index), i + 1, { active: focus?.id === stop.id, faded: index !== selected })}
            zIndexOffset={index === selected ? 1000 : 0}
            title={stop.place.name}
            ref={(marker) => {
              if (marker) markerRefs.current[stop.id] = marker
            }}
            eventHandlers={{ click: () => onSelectStop(stop.id, index) }}
          >
            <Popup>
              <PlacePopup stop={stop} number={i + 1} dayLabel={day.label} symbol={symbol} />
            </Popup>
          </Marker>
        )),
      )}

      <Marker position={[trip.base.lat, trip.base.lng]} icon={baseIcon} zIndexOffset={2000} title={trip.base.name}>
        <Popup>
          <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-steel">Base</p>
          <p className="font-semibold">{trip.base.name}</p>
        </Popup>
      </Marker>
    </MapContainer>
  )
}
