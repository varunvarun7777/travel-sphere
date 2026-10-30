import { IconPlus } from './Icons'
import { btn, panel } from './ui'

/** Places the planner had to leave out, with the reason and a way back in. */
export default function UnplacedList({ items, targetLabel, editable, busy, onAddBack }) {
  if (!items?.length) return null
  return (
    <section className={`${panel} mt-8 p-4 print:hidden`} aria-labelledby="unplaced-heading">
      <h2 id="unplaced-heading" className="font-display wide text-lg font-extrabold">
        Didn’t make the cut
      </h2>
      <p className="text-sm text-steel">These didn’t fit your days. Add one back and TravelSphere re-times the day around it.</p>
      <ul className="mt-3 divide-y divide-rule">
        {items.map((u) => (
          <li key={u.id} className="flex items-center gap-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{u.name}</p>
              <p className="font-mono text-xs text-steel">{u.reason}</p>
            </div>
            {editable && (
              <button type="button" className={btn} disabled={busy} onClick={() => onAddBack(u)}>
                <IconPlus /> Add to {targetLabel}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
