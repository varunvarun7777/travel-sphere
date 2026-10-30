import { CircleMarker, MapContainer, Marker, Tooltip } from 'react-leaflet'
import { AutoResize, BaseTiles, FitBounds, baseIcon } from './mapParts'

const STYLE = {
  none: { color: '#5A6570', fillColor: '#FFFFFF', fillOpacity: 1, weight: 2, radius: 6 },
  must: { color: '#11181F', fillColor: '#FFC20E', fillOpacity: 1, weight: 2.5, radius: 9 },
  avoid: { color: '#11181F', fillColor: '#11181F', fillOpacity: 0.35, weight: 1.5, radius: 6 },
}
const STATE_LABEL = { none: 'Click to make it a must-see', must: 'Must see — click to skip it', avoid: 'Skipped — click to clear' }

/** All of a city's places as dots; clicking a dot cycles none → must-see → skip. */
export default function CityMap({ city, places, stateOf, onCycle, base }) {
  const points = places.map((p) => [p.lat, p.lng])
  return (
    <MapContainer center={[city.lat, city.lng]} zoom={13} scrollWheelZoom fadeAnimation={false} className="h-full w-full">
      <BaseTiles />
      <AutoResize />
      <FitBounds points={points} fitKey={`${city.id}-${places.length}`} />
      {places.map((p) => {
        const state = stateOf(p.id)
        return (
          <CircleMarker key={`${p.id}-${state}`} center={[p.lat, p.lng]} pathOptions={STYLE[state]} radius={STYLE[state].radius} eventHandlers={{ click: () => onCycle(p.id) }}>
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{p.name}</strong>
              <br />
              {STATE_LABEL[state]}
            </Tooltip>
          </CircleMarker>
        )
      })}
      <Marker position={base ? [base.lat, base.lng] : [city.lat, city.lng]} icon={baseIcon} title={base ? base.name : `${city.name} centre`}>
        <Tooltip direction="top" offset={[0, -8]}>
          {base ? `Staying at ${base.name}` : `${city.name} centre (your base)`}
        </Tooltip>
      </Marker>
    </MapContainer>
  )
}
