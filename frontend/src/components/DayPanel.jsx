import { useState } from 'react'
import { formatKm, formatPrice } from '../lib/format'
import { lineColor } from '../lib/lines'
import { googleMapsDayUrl } from '../lib/maps'
import AddStopPanel from './AddStopPanel'
import { IconExternal, IconPlus, IconRoute, IconWarning } from './Icons'
import MetroLine from './MetroLine'
import { btn, btnPrimary, signalTag } from './ui'

const BRIEF_SOURCE = { gemini: 'Written by Gemini', claude: 'Written by Claude', rules: 'Written from TravelSphere’s templates' }

export function DayNotes({ note, source }) {
  if (!note) return null
  return (
    <div className="mt-4 border-l-4 border-ink bg-panel px-4 py-3">
      <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-steel">Day notes · {BRIEF_SOURCE[source] || BRIEF_SOURCE.rules}</p>
      <p className="mt-1 font-display wide text-lg font-extrabold leading-tight">{note.title}</p>
      {note.summary && <p className="mt-1 text-sm">{note.summary}</p>}
      {note.tips?.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {note.tips.map((tip) => (
            <li key={tip} className="flex gap-2">
              <span aria-hidden className="mt-[7px] size-1.5 shrink-0 bg-ink" />
              {tip}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function DayWarnings({ warnings }) {
  if (!warnings.length) return null
  return (
    <ul className="mt-3 flex flex-wrap gap-2" aria-label="Warnings for this day">
      {warnings.map((w) => (
        <li key={w} className={signalTag}>
          <IconWarning /> {w}
        </li>
      ))}
    </ul>
  )
}

export function dayWarnings(day, weather, rainRisk) {
  const list = [...(day.warnings || [])]
  if (rainRisk) list.push(`${weather.rain}% chance of rain — outdoor stops may be a washout`)
  return list
}

/** Header, notes, warnings, timeline and day actions for the selected day. */
export default function DayPanel({ trip, index, weather, rainRisk, editable, busy, focus, onFocusStop, editor, cityPlaces }) {
  const [adding, setAdding] = useState(false)
  const day = trip.days[index]
  const color = lineColor(index)
  const m = day.metrics || {}
  const mapsUrl = googleMapsDayUrl(trip.base, day, trip.prefs.mode)
  const note = trip.brief?.days?.find((d) => d.date === day.date)
  const otherDays = trip.days.map((d, i) => ({ index: i, label: d.label })).filter((d) => d.index !== index)

  const actions = {
    reorder: (id, to) => editor.reorder(index, id, to),
    toggleLock: (id) => editor.toggleLock(index, id),
    remove: (id) => editor.remove(index, id),
    moveToDay: (id, to) => editor.moveToDay(index, id, to),
  }

  return (
    <section aria-labelledby={`day-${index}-heading`}>
      <div className="flex flex-wrap items-end justify-between gap-3 border-b-[6px] pb-3" style={{ borderColor: color }}>
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-steel">Line {index + 1}</p>
          <h2 id={`day-${index}-heading`} className="font-display wide text-2xl font-black leading-none">
            {day.label}
          </h2>
          <p className="mt-1.5 font-mono text-xs text-steel">
            {m.stops ?? day.stops.length} stops · {formatKm(m.km)} · {formatKm(m.walk_km)} on foot · {formatPrice(m.fees, trip.city.symbol)} entry
            {m.finish && ` · back ${m.finish}`}
            {day.sunset && ` · sunset ${day.sunset}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 print:hidden">
          {editable && (
            <button type="button" className={btnPrimary} disabled={busy || day.stops.length < 2} onClick={() => editor.optimise(index)}>
              <IconRoute /> Optimise route
            </button>
          )}
          {mapsUrl && (
            <a className={btn} href={mapsUrl} target="_blank" rel="noreferrer">
              Open in Google Maps <IconExternal />
            </a>
          )}
        </div>
      </div>

      <p role="status" className="mt-2 h-5 font-mono text-xs text-steel print:hidden">
        {busy ? 'Re-timing this day…' : ''}
      </p>

      <DayNotes note={note} source={trip.brief?.source} />
      <DayWarnings warnings={dayWarnings(day, weather, rainRisk)} />

      {day.stops.length === 0 && (
        <p className="mt-4 rounded-md border border-dashed border-rule px-4 py-3 text-sm text-steel">
          No stops on this day yet. Add one below{editable && trip.days.length > 1 ? ', or drag a stop onto this day’s tab' : ''}.
        </p>
      )}

      <div className="mt-4">
        <MetroLine
          day={day}
          color={color}
          base={trip.base}
          symbol={trip.city.symbol}
          editable={editable}
          busy={busy}
          focus={focus}
          onFocusStop={onFocusStop}
          actions={actions}
          otherDays={otherDays}
        />
      </div>

      {editable &&
        (adding ? (
          <AddStopPanel
            trip={trip}
            dayIndex={index}
            cityPlaces={cityPlaces}
            busy={busy}
            onAdd={(place) => editor.addStop(index, place)}
            onClose={() => setAdding(false)}
          />
        ) : (
          <button type="button" className={`${btn} mt-2 print:hidden`} onClick={() => setAdding(true)}>
            <IconPlus /> Add a stop
          </button>
        ))}
    </section>
  )
}
