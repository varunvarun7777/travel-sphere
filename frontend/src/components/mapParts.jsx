import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { TileLayer, useMap } from 'react-leaflet'
import { prefersReducedMotion } from '../lib/geo'

export function BaseTiles() {
  return (
    <TileLayer
      url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      className="wl-tiles"
      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      subdomains="abcd"
      maxZoom={20}
    />
  )
}

const iconCache = new Map()

/** Numbered roundel in a day colour. Cached so markers keep the same icon object between renders. */
export function stationIcon(color, number, { active = false, faded = false } = {}) {
  const key = `${color}|${number}|${active}|${faded}`
  if (!iconCache.has(key)) {
    const classes = ['wl-station', active && 'is-active', faded && 'is-faded'].filter(Boolean).join(' ')
    iconCache.set(
      key,
      L.divIcon({
        className: '',
        html: `<span class="${classes}" style="--c:${color}">${number}</span>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
      }),
    )
  }
  return iconCache.get(key)
}

export const baseIcon = L.divIcon({
  className: '',
  html: '<span class="wl-base"></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
  popupAnchor: [0, -9],
})

/** Fits the map to `points` whenever `fitKey` changes. */
export function FitBounds({ points, fitKey }) {
  const map = useMap()
  const latest = useRef(points)
  latest.current = points

  useEffect(() => {
    const pts = latest.current
    if (!pts.length) return
    const animate = !prefersReducedMotion()
    if (pts.length === 1) map.setView(pts[0], 15, { animate })
    else map.fitBounds(pts, { padding: [40, 40], maxZoom: 16, animate })
  }, [map, fitKey])
  return null
}

/** Keeps Leaflet's size in sync when its container changes size (e.g. stacking on mobile). */
export function AutoResize() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}
