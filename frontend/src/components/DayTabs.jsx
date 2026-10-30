import { splitDayLabel } from '../lib/format'
import { lineColor } from '../lib/lines'
import { STOP_DRAG_TYPE } from './MetroLine'

function WeatherChip({ weather }) {
  if (!weather) return null
  return (
    <span className="font-mono text-[11px] text-steel" title={`${weather.label}, ${weather.rain}% chance of rain`}>
      {weather.max}°/{weather.min}° · {weather.rain}% rain
    </span>
  )
}

/** Day selector: one roundel per line. Stops can be dropped on a tab to move them to that day. */
export default function DayTabs({ days, selected, onSelect, allDays, onToggleAll, weather, rainRisk, onDropStop }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2 print:hidden">
      <div role="tablist" aria-label="Days" className="-mx-1 flex flex-1 gap-2 overflow-x-auto px-1 pb-1">
        {days.map((day, i) => {
          const { weekday, date } = splitDayLabel(day.label)
          const active = i === selected
          return (
            <button
              key={day.date}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onSelect(i)}
              onDragOver={(e) => {
                if (onDropStop && e.dataTransfer.types.includes(STOP_DRAG_TYPE)) e.preventDefault()
              }}
              onDrop={(e) => {
                const raw = e.dataTransfer.getData(STOP_DRAG_TYPE)
                if (!raw || !onDropStop) return
                e.preventDefault()
                onDropStop(JSON.parse(raw), i)
              }}
              className={`relative flex min-w-[9.5rem] shrink-0 items-center gap-3 rounded-md border px-3 py-2 text-left ${
                active ? 'border-ink bg-white' : 'border-rule bg-panel hover:border-ink'
              }`}
            >
              <span
                className="grid size-8 shrink-0 place-items-center rounded-full font-display wide text-sm font-black text-white"
                style={{ background: lineColor(i) }}
                aria-hidden
              >
                {i + 1}
              </span>
              <span className="flex flex-col leading-tight">
                <span className="font-display wide font-extrabold">
                  {weekday} <span className="font-mono text-xs font-medium text-steel">{date}</span>
                </span>
                <WeatherChip weather={weather[day.date]} />
              </span>
              {rainRisk[i] && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-signal" title="Rain likely on outdoor stops" />}
              {active && <span aria-hidden className="absolute inset-x-0 -bottom-px h-1 rounded-b-md bg-signal" />}
            </button>
          )
        })}
      </div>
      <button
        type="button"
        aria-pressed={allDays}
        onClick={onToggleAll}
        className={`shrink-0 rounded-md border px-3 py-2 text-sm font-semibold ${allDays ? 'border-ink bg-ink text-white' : 'border-rule bg-panel hover:border-ink'}`}
      >
        All days on map
      </button>
    </div>
  )
}
