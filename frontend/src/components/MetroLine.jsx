import { useEffect, useState } from 'react'
import { BEST_TIME, closedDaysLabel, formatKm, formatMinutes, formatPrice, hoursLabel, humanize } from '../lib/format'
import { prefersReducedMotion } from '../lib/geo'
import { IconClose, IconDown, IconGrip, IconLock, IconUnlock, IconUp, IconWarning } from './Icons'
import { iconBtn, signalTag } from './ui'

export const STOP_DRAG_TYPE = 'text/x-travelsphere-stop'
const ROW = 'grid grid-cols-[3.75rem_2.5rem_minmax(0,1fr)] gap-x-2 sm:grid-cols-[4.25rem_2.75rem_minmax(0,1fr)] sm:gap-x-3'
const MARKER_CENTER = 20 // px from a row's top to the centre of its marker

export const stopElementId = (date, id) => `stop-${date}-${id}`.replace(/[^\w-]/g, '-')

/** The vertical line through a row. Walk legs are dotted, everything else is a solid bar. */
function Track({ color, dotted = false, from = false, to = false }) {
  const style = dotted
    ? { left: '50%', marginLeft: -3, borderLeft: `6px dotted ${color}` }
    : { left: '50%', marginLeft: -4, width: 8, background: color }
  style.top = from ? MARKER_CENTER : 0
  if (to) style.height = MARKER_CENTER
  else style.bottom = 0
  return <span aria-hidden className="absolute" style={style} />
}

function Terminus({ time, label, place, color, first }) {
  return (
    <li className={ROW}>
      <div className="pt-2.5 text-right font-mono text-[13px] font-semibold tabular-nums">{time}</div>
      <div className="relative min-h-12">
        <Track color={color} from={first} to={!first} />
        <span aria-hidden className="absolute left-1/2 top-[11px] size-[18px] -translate-x-1/2 border-[3px] border-white bg-ink outline outline-1 outline-ink" />
      </div>
      <div className="pb-4 pt-2">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-steel">{label}</p>
        <p className="font-semibold">{place}</p>
      </div>
    </li>
  )
}

function TravelLeg({ leg, color }) {
  return (
    <li className={ROW}>
      <div />
      <div className="relative min-h-9">
        <Track color={color} dotted={leg.mode === 'walk'} />
      </div>
      <div className="flex items-center py-2 font-mono text-xs text-steel">
        {formatMinutes(leg.minutes)} · {leg.mode} · {formatKm(leg.km)}
      </div>
    </li>
  )
}

function LunchRow({ item, color }) {
  return (
    <li className={ROW}>
      <div className="pt-2.5 text-right font-mono text-[13px] tabular-nums">
        <div className="font-semibold">{item.start}</div>
        <div className="text-steel">{item.end}</div>
      </div>
      <div className="relative">
        <Track color={color} />
        <span aria-hidden className="absolute left-1/2 top-[10px] h-5 w-8 -translate-x-1/2 rounded-md border-[3px] border-ink bg-white" />
      </div>
      <div className="pb-4 pt-2">
        <p className="font-display wide font-extrabold">Lunch break</p>
        {item.suggestion && <p className="text-sm text-steel">{item.suggestion}</p>}
      </div>
    </li>
  )
}

function SunsetRow({ time, color }) {
  return (
    <li className={ROW} aria-label={`Sunset at ${time}`}>
      <div className="pt-1 text-right font-mono text-xs text-steel tabular-nums">{time}</div>
      <div className="relative min-h-7">
        <Track color={color} />
        <span aria-hidden className="absolute left-1/2 top-[11px] h-[3px] w-7 -translate-x-1/2 bg-signal" />
      </div>
      <div className="pt-1 font-mono text-xs uppercase tracking-[0.14em] text-steel">Sunset</div>
    </li>
  )
}

function Station({ item, number, day, color, symbol, editable, busy, focused, onFocusStop, actions, otherDays, drag }) {
  const p = item.place
  const locked = (day.locked || []).includes(item.id)
  const index = day.stops.indexOf(item.id)
  const meta = [humanize(p.kind), formatMinutes(p.duration), formatPrice(p.price, symbol), hoursLabel(p), closedDaysLabel(p.closed_days)]
  const isDropTarget = drag.overId === item.id && drag.dragId && drag.dragId !== item.id

  return (
    <li
      id={stopElementId(day.date, item.id)}
      className={`${ROW} scroll-mt-24`}
      draggable={editable && !busy}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', p.name)
        e.dataTransfer.setData(STOP_DRAG_TYPE, JSON.stringify({ id: item.id, date: day.date }))
        drag.setDragId(item.id)
      }}
      onDragEnd={() => drag.reset()}
      onDragOver={(e) => {
        if (!drag.dragId) return
        e.preventDefault()
        drag.setOverId(item.id)
      }}
      onDrop={(e) => {
        if (!drag.dragId) return
        e.preventDefault()
        if (drag.dragId !== item.id) actions.reorder(drag.dragId, index)
        drag.reset()
      }}
    >
      <div className="pt-2.5 text-right font-mono text-[13px] tabular-nums">
        {item.arrive && item.arrive !== item.start && <div className="text-[11px] text-steel">arr {item.arrive}</div>}
        <div className="font-semibold">{item.start}</div>
        <div className="text-steel">{item.end}</div>
      </div>
      <div className="relative">
        <Track color={color} />
        <span
          aria-hidden
          className={`absolute left-1/2 top-[6px] grid size-7 -translate-x-1/2 place-items-center rounded-full border-[5px] bg-white font-display wide text-[11px] font-black ${
            focused ? 'outline-3 outline-offset-1 outline-signal' : ''
          }`}
          style={{ borderColor: color }}
        >
          {number}
        </span>
      </div>
      <div className="relative pb-4">
        {isDropTarget && <span aria-hidden className="absolute -top-1 left-0 right-0 h-1 rounded-sm bg-signal" />}
        <div className={`rounded-md border px-3 py-2 ${focused ? 'border-ink bg-white' : 'border-transparent'}`}>
          <div className="flex items-start gap-2">
            {editable && (
              <span className="mt-1 hidden cursor-grab text-steel sm:block" title="Drag to reorder" aria-hidden>
                <IconGrip />
              </span>
            )}
            <button
              type="button"
              onClick={() => onFocusStop(item.id)}
              className="text-left font-display wide text-lg font-extrabold leading-tight hover:underline"
            >
              {p.name}
            </button>
          </div>
          <p className="mt-1 font-mono text-xs text-steel">{meta.filter(Boolean).join(' · ')}</p>
          {(item.wait > 0 || locked || BEST_TIME[p.best] || p.custom) && (
            <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs">
              {locked && (
                <span className="inline-flex items-center gap-1 rounded-sm border border-ink px-1.5 py-0.5 font-semibold">
                  <IconLock /> Fixed position
                </span>
              )}
              {item.wait > 0 && <span className="rounded-sm border border-rule px-1.5 py-0.5 text-steel">Waits {formatMinutes(item.wait)} for opening</span>}
              {BEST_TIME[p.best] && <span className="rounded-sm border border-rule px-1.5 py-0.5 text-steel">{BEST_TIME[p.best]}</span>}
              {p.custom && <span className="rounded-sm border border-rule px-1.5 py-0.5 text-steel">Your place</span>}
            </div>
          )}
          {item.warnings?.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {item.warnings.map((w) => (
                <li key={w} className={signalTag}>
                  <IconWarning /> {w}
                </li>
              ))}
            </ul>
          )}
          {editable && (
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5 print:hidden">
              <button type="button" className={iconBtn} disabled={busy || index === 0} onClick={() => actions.reorder(item.id, index - 1)} aria-label={`Move ${p.name} earlier`} title="Move earlier">
                <IconUp />
              </button>
              <button
                type="button"
                className={iconBtn}
                disabled={busy || index === day.stops.length - 1}
                onClick={() => actions.reorder(item.id, index + 1)}
                aria-label={`Move ${p.name} later`}
                title="Move later"
              >
                <IconDown />
              </button>
              <button
                type="button"
                className={`${iconBtn} ${locked ? 'border-ink bg-ink text-white hover:bg-black' : ''}`}
                disabled={busy}
                onClick={() => actions.toggleLock(item.id)}
                aria-pressed={locked}
                aria-label={locked ? `Unlock ${p.name}` : `Lock ${p.name} in place`}
                title={locked ? 'Unlock: let Optimise route move this stop' : 'Lock: keep this stop in place when optimising'}
              >
                {locked ? <IconLock /> : <IconUnlock />}
              </button>
              {otherDays.length > 0 && (
                <select
                  className="h-8 rounded-md border border-rule bg-panel px-2 text-xs font-semibold hover:border-ink"
                  value=""
                  disabled={busy}
                  aria-label={`Move ${p.name} to another day`}
                  onChange={(e) => actions.moveToDay(item.id, Number(e.target.value))}
                >
                  <option value="" disabled>
                    Move to…
                  </option>
                  {otherDays.map((d) => (
                    <option key={d.index} value={d.index}>
                      Line {d.index + 1} · {d.label}
                    </option>
                  ))}
                </select>
              )}
              <button type="button" className={iconBtn} disabled={busy} onClick={() => actions.remove(item.id)} aria-label={`Remove ${p.name}`} title="Remove from this day">
                <IconClose />
              </button>
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

/** Index of the first stop or lunch that starts at or after sunset; -1 if sunset is outside the day. */
function sunsetPosition(day) {
  if (!day.sunset) return -1
  const idx = day.items.findIndex((it) => it.type !== 'travel' && it.start >= day.sunset)
  if (idx >= 0) return idx
  return (day.metrics?.finish || day.end) >= day.sunset ? day.items.length : -1
}

/**
 * The signature metro-line timeline for one day.
 * actions: { reorder(id, toIndex), toggleLock(id), remove(id), moveToDay(id, dayIndex) } — only used when editable.
 */
export default function MetroLine({ day, color, base, symbol, editable = false, busy = false, focus, onFocusStop, actions, otherDays = [] }) {
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)
  const drag = {
    dragId,
    overId,
    setDragId,
    setOverId,
    reset: () => {
      setDragId(null)
      setOverId(null)
    },
  }

  useEffect(() => {
    if (focus?.source !== 'map') return
    document.getElementById(stopElementId(day.date, focus.id))?.scrollIntoView({
      block: 'center',
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    })
  }, [focus, day.date])

  const sunsetAt = sunsetPosition(day)
  let stopNumber = 0
  const rows = day.items.map((item, i) => {
    let row
    if (item.type === 'travel') row = <TravelLeg key={`t${i}`} leg={item} color={color} />
    else if (item.type === 'lunch') row = <LunchRow key={`l${i}`} item={item} color={color} />
    else {
      stopNumber += 1
      row = (
        <Station
          key={item.id}
          item={item}
          number={stopNumber}
          day={day}
          color={color}
          symbol={symbol}
          editable={editable}
          busy={busy}
          focused={focus?.id === item.id}
          onFocusStop={onFocusStop}
          actions={actions}
          otherDays={otherDays}
          drag={drag}
        />
      )
    }
    return i === sunsetAt ? [<SunsetRow key="sunset" time={day.sunset} color={color} />, row] : row
  })

  return (
    <ol aria-label={`Itinerary for ${day.label}`} className={busy ? 'opacity-60' : ''}>
      <Terminus first time={day.start} label="Start" place={base.name} color={color} />
      {rows}
      {sunsetAt === day.items.length && <SunsetRow time={day.sunset} color={color} />}
      <Terminus time={day.metrics?.finish || day.end} label="Back at base" place={base.name} color={color} />
    </ol>
  )
}
