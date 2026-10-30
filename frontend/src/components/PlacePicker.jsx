import { useState } from 'react'
import { formatMinutes, humanize } from '../lib/format'
import { IconClose } from './Icons'
import { fieldLabel, input } from './ui'

function Chosen({ label, ids, byId, onClear, tone }) {
  if (!ids.length) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={`${fieldLabel} mr-1`}>{label}</span>
      {ids.map((id) => (
        <span
          key={id}
          className={`inline-flex items-center gap-1 rounded-sm border py-0.5 pl-2 pr-1 text-sm ${tone === 'must' ? 'border-ink bg-signal' : 'border-rule bg-white text-steel line-through decoration-1'}`}
        >
          {byId.get(id)?.name ?? humanize(id)}
          <button type="button" onClick={() => onClear(id)} className="grid size-5 place-items-center rounded-sm no-underline hover:bg-ink/10" aria-label={`Clear ${byId.get(id)?.name ?? id}`}>
            <IconClose />
          </button>
        </span>
      ))}
    </div>
  )
}

/** Searchable list of the city's places with must-see and skip toggles. */
export default function PlacePicker({ places, mustSee, avoid, onSet }) {
  const [query, setQuery] = useState('')
  const byId = new Map(places.map((p) => [p.id, p]))
  const q = query.trim().toLowerCase()
  const shown = places
    .filter((p) => !q || p.name.toLowerCase().includes(q) || p.kind.toLowerCase().includes(q) || p.tags.some((t) => t.includes(q)))
    .sort((a, b) => b.popularity - a.popularity)

  const toggle = (id, state) => {
    const current = mustSee.includes(id) ? 'must' : avoid.includes(id) ? 'avoid' : 'none'
    onSet(id, current === state ? 'none' : state)
  }

  return (
    <div>
      <div className="space-y-2">
        <Chosen label="Must see" ids={mustSee} byId={byId} tone="must" onClear={(id) => onSet(id, 'none')} />
        <Chosen label="Skip" ids={avoid} byId={byId} tone="avoid" onClear={(id) => onSet(id, 'none')} />
      </div>
      <label className="mt-3 block">
        <span className="sr-only">Search places</span>
        <input className={input} type="search" placeholder={`Search ${places.length} places by name, kind or tag`} value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>
      <ul className="mt-2 max-h-72 divide-y divide-rule overflow-y-auto rounded-md border border-rule bg-white">
        {shown.length === 0 && <li className="px-3 py-3 text-sm text-steel">{places.length ? 'No places match that search.' : 'Loading places…'}</li>}
        {shown.map((p) => {
          const must = mustSee.includes(p.id)
          const skip = avoid.includes(p.id)
          return (
            <li key={p.id} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className={`truncate text-sm font-semibold ${skip ? 'text-steel line-through' : ''}`}>{p.name}</p>
                <p className="font-mono text-[11px] text-steel">
                  {humanize(p.kind)} · {formatMinutes(p.duration)}
                </p>
              </div>
              <div className="flex shrink-0 gap-1" role="group" aria-label={p.name}>
                <button
                  type="button"
                  aria-pressed={must}
                  onClick={() => toggle(p.id, 'must')}
                  className={`rounded-md border px-2 py-1 text-xs font-semibold ${must ? 'border-ink bg-signal' : 'border-rule hover:border-ink'}`}
                >
                  Must see
                </button>
                <button
                  type="button"
                  aria-pressed={skip}
                  onClick={() => toggle(p.id, 'avoid')}
                  className={`rounded-md border px-2 py-1 text-xs font-semibold ${skip ? 'border-ink bg-ink text-white' : 'border-rule hover:border-ink'}`}
                >
                  Skip
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
