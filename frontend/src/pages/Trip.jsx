import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import DayPanel, { DayNotes, DayWarnings, dayWarnings } from '../components/DayPanel'
import DayTabs from '../components/DayTabs'
import MetricsStrip from '../components/MetricsStrip'
import MetroLine from '../components/MetroLine'
import { Toast, useToast } from '../components/Toast'
import TripMap from '../components/TripMap'
import UnplacedList from '../components/UnplacedList'
import { btn, btnPrimary, input, panel } from '../components/ui'
import { useTripEditor } from '../hooks/useTripEditor'
import { useWeather } from '../hooks/useWeather'
import { downloadIcs } from '../lib/ics'
import { formatDateRange } from '../lib/format'
import { lineColor, MODES } from '../lib/lines'
import { clearDraft, defaultTitle, hasNatureStops, readDraft, writeDraft } from '../lib/trip'

const RAIN_THRESHOLD = 60

function Message({ title, children }) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
      <div className={`${panel} p-6`}>
        <h1 className="font-display wide text-2xl font-black">{title}</h1>
        <div className="mt-2 text-steel">{children}</div>
      </div>
    </main>
  )
}

/** Loads a trip for /trip (draft), /trips/:id (saved) or /s/:slug (shared, read-only). */
export default function TripPage({ mode }) {
  const { id, slug } = useParams()
  const location = useLocation()
  const [state, setState] = useState({ status: 'loading' })

  useEffect(() => {
    if (mode === 'draft') {
      const draft = readDraft()
      setState(draft?.trip ? { status: 'ready', trip: draft.trip, record: { title: draft.title } } : { status: 'empty' })
      return undefined
    }
    let cancelled = false
    setState({ status: 'loading' })
    const load = mode === 'saved' ? api.trip(id) : api.sharedTrip(slug)
    load
      .then((r) => {
        if (!cancelled) setState({ status: 'ready', trip: r.data, record: { id: r.id, title: r.title, share_slug: r.share_slug } })
      })
      .catch((error) => {
        if (!cancelled) setState({ status: 'error', error })
      })
    return () => {
      cancelled = true
    }
  }, [mode, id, slug])

  if (state.status === 'loading') return <Message title="Loading trip…">Fetching your itinerary.</Message>
  if (state.status === 'empty') {
    return (
      <Message title="No trip in progress">
        <p>Plan a trip first, then you can reorder stops, optimise routes and save it here.</p>
        <Link to="/" className={`${btnPrimary} mt-4`}>
          Plan my days
        </Link>
      </Message>
    )
  }
  if (state.status === 'error') {
    const needsLogin = state.error.status === 401
    return (
      <Message title={needsLogin ? 'Sign in to see this trip' : 'We couldn’t open this trip'}>
        <p>{needsLogin ? 'Saved trips are private. Sign in with the account that saved it.' : state.error.message}</p>
        <Link to={needsLogin ? `/login?next=${encodeURIComponent(location.pathname)}` : '/'} className={`${btnPrimary} mt-4`}>
          {needsLogin ? 'Sign in' : 'Plan a new trip'}
        </Link>
      </Message>
    )
  }
  return <TripView key={`${mode}-${state.record.id ?? 'draft'}`} mode={mode} initialTrip={state.trip} initialRecord={state.record} />
}

function TripView({ mode, initialTrip, initialRecord }) {
  const readOnly = mode === 'shared'
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [toast, notify] = useToast()
  const editor = useTripEditor(initialTrip, notify)
  const { trip, busyDays } = editor

  const [record, setRecord] = useState(initialRecord)
  const [title, setTitle] = useState(initialRecord.title || defaultTitle(initialTrip))
  const [savedState, setSavedState] = useState({ trip: initialTrip, title })
  const [selected, setSelected] = useState(0)
  const [allDays, setAllDays] = useState(false)
  const [focus, setFocus] = useState(null)
  const [cityPlaces, setCityPlaces] = useState([])
  const [saving, setSaving] = useState(false)
  const [writingNotes, setWritingNotes] = useState(false)
  const [makingPdf, setMakingPdf] = useState(false)

  const weather = useWeather(trip.city.lat, trip.city.lng, trip.days.map((d) => d.date))
  const rainRisk = trip.days.map((d) => (weather[d.date]?.rain ?? 0) >= RAIN_THRESHOLD && hasNatureStops(d))
  const dirty = mode === 'saved' && (trip !== savedState.trip || title !== savedState.title)
  const busy = busyDays.length > 0

  useEffect(() => {
    if (location.state?.justSaved) notify('Trip saved. Copy the share link to send it to someone.')
  }, [location.state, notify])

  useEffect(() => {
    if (readOnly) return
    api
      .places(trip.city.id)
      .then(setCityPlaces)
      .catch(() => notify('Couldn’t load suggestions for this city. Adding stops will work once the server is reachable.', 'error'))
  }, [trip.city.id, readOnly, notify])

  useEffect(() => {
    if (mode === 'draft') writeDraft({ trip, title })
  }, [mode, trip, title])

  function focusStop(id, source, dayIndex = selected) {
    setSelected(dayIndex)
    setFocus({ id, source, at: Date.now() })
  }

  async function save() {
    if (!user) {
      navigate(`/login?next=${encodeURIComponent(location.pathname)}`, { state: { reason: 'save' } })
      return
    }
    setSaving(true)
    try {
      if (record.id) {
        const saved = await api.updateTrip(record.id, title, trip)
        setRecord({ ...record, share_slug: saved.share_slug })
        setSavedState({ trip, title })
        notify('Changes saved.')
      } else {
        const saved = await api.createTrip(title, trip)
        clearDraft()
        navigate(`/trips/${saved.id}`, { replace: true, state: { justSaved: true } })
      }
    } catch (err) {
      notify(err.status === 401 ? 'Your session expired. Sign in again, then save — your draft is kept.' : err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function copyShareLink() {
    const url = `${window.location.origin}/s/${record.share_slug}`
    try {
      await navigator.clipboard.writeText(url)
      notify('Share link copied. Anyone with it can view this trip.')
    } catch {
      notify(`Couldn’t copy automatically. Your link is ${url}`, 'error')
    }
  }

  async function downloadPdf() {
    setMakingPdf(true)
    try {
      const file = await api.pdf({ ...trip, title })
      const url = URL.createObjectURL(file)
      const link = Object.assign(document.createElement('a'), { href: url, download: `travelsphere-${trip.city.id}-${startDate}.pdf` })
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      notify(trip.brief ? 'PDF downloaded.' : 'PDF downloaded. Write day notes first to include tips in it.')
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setMakingPdf(false)
    }
  }

  async function writeNotes() {
    setWritingNotes(true)
    try {
      const brief = await api.brief(trip)
      editor.setBrief(brief)
      const writer = { gemini: 'Gemini', claude: 'Claude' }[brief.source]
      notify(writer ? `Day notes written by ${writer}.` : 'Day notes written from templates (the AI service didn’t answer).')
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setWritingNotes(false)
    }
  }

  const startDate = trip.days[0]?.date ?? trip.prefs.start_date

  return (
    <main className="mx-auto max-w-[1440px] px-4 pb-16 pt-6 sm:px-6">
      {readOnly && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-md border border-ink bg-white px-4 py-3 text-sm print:hidden">
          <span>
            <strong>Shared trip.</strong> You’re viewing someone’s itinerary; changes aren’t possible here.
          </span>
          <Link to="/" className={btn}>
            Plan your own
          </Link>
        </div>
      )}

      <header>
        <p className="font-mono text-xs uppercase tracking-[0.16em] text-steel">
          {trip.city.country} · {formatDateRange(startDate, trip.days.length)}
        </p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="font-display wider text-5xl font-black leading-[0.9] tracking-tight sm:text-6xl">{trip.city.name}</h1>
            {readOnly ? (
              <p className="mt-2 text-lg font-semibold">{title}</p>
            ) : (
              <label className="mt-2 block">
                <span className="sr-only">Trip title</span>
                <input
                  className={`${input} max-w-md border-transparent bg-transparent px-0 text-lg font-semibold hover:border-rule focus:bg-white focus:px-2 print:hidden`}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
                <span className="hidden text-lg font-semibold print:block">{title}</span>
              </label>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            {!readOnly && (
              <>
                <button type="button" className={btn} onClick={writeNotes} disabled={writingNotes || busy}>
                  {writingNotes ? 'Writing notes…' : trip.brief ? 'Rewrite day notes' : 'Write day notes'}
                </button>
                <button type="button" className={btnPrimary} onClick={save} disabled={saving || busy || (mode === 'saved' && !dirty)}>
                  {saving ? 'Saving…' : mode === 'saved' ? (dirty ? 'Save changes' : 'Saved') : 'Save trip'}
                </button>
              </>
            )}
            {record.share_slug && !readOnly && (
              <button type="button" className={btn} onClick={copyShareLink}>
                Copy share link
              </button>
            )}
            <button type="button" className={btn} onClick={() => downloadIcs(trip, `travelsphere-${trip.city.id}-${startDate}.ics`)}>
              Add to calendar
            </button>
            <button type="button" className={btn} onClick={() => window.print()}>
              Print
            </button>
            <button type="button" className={btnPrimary} onClick={downloadPdf} disabled={makingPdf || busy}>
              {makingPdf ? 'Making PDF…' : 'Download PDF'}
            </button>
          </div>
        </div>
        {mode === 'draft' && !user && (
          <p className="mt-2 text-sm text-steel print:hidden">This is a draft in this browser tab. Sign in and save it to keep it and get a share link.</p>
        )}
        <MetricsStrip metrics={trip.metrics} symbol={trip.city.symbol} />
      </header>

      {!readOnly && (
        <div className="mt-4 flex flex-wrap items-center gap-2 print:hidden" role="group" aria-label="Getting around for the whole trip">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-steel">Getting around</span>
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={trip.prefs.mode === m.id}
              disabled={busy}
              title={m.hint}
              onClick={() => editor.setMode(m.id)}
              className={`rounded-md border px-3 py-1.5 text-sm font-semibold disabled:opacity-50 ${
                trip.prefs.mode === m.id ? 'border-ink bg-ink text-white' : 'border-rule bg-panel hover:border-ink'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}

      <div className="mt-5">
        <DayTabs
          days={trip.days}
          selected={selected}
          onSelect={(i) => {
            setSelected(i)
            setFocus(null)
          }}
          allDays={allDays}
          onToggleAll={() => setAllDays((v) => !v)}
          weather={weather}
          rainRisk={rainRisk}
          onDropStop={readOnly || busy ? null : ({ id, date }, to) => editor.moveToDay(trip.days.findIndex((d) => d.date === date), id, to)}
        />
      </div>

      <div className="mt-5 grid gap-6 print:hidden lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="lg:order-2">
          <div className="h-[46vh] min-h-[300px] overflow-hidden rounded-md border border-rule lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)]">
            <TripMap trip={trip} selected={selected} allDays={allDays} focus={focus} onSelectStop={(id, dayIndex) => focusStop(id, 'map', dayIndex)} />
          </div>
        </div>
        <div className="min-w-0 lg:order-1">
          <DayPanel
            key={selected}
            trip={trip}
            index={selected}
            weather={weather[trip.days[selected].date]}
            rainRisk={rainRisk[selected]}
            editable={!readOnly}
            busy={busyDays.includes(selected)}
            focus={focus}
            onFocusStop={(id) => focusStop(id, 'list')}
            editor={editor}
            cityPlaces={cityPlaces}
          />
          <UnplacedList
            items={trip.unplaced}
            editable={!readOnly}
            busy={busy}
            targetLabel={`line ${selected + 1}`}
            onAddBack={(u) => editor.addStop(selected, { id: u.id, name: u.name })}
          />
        </div>
      </div>

      <PrintItinerary trip={trip} weather={weather} rainRisk={rainRisk} />
      <Toast toast={toast} />
    </main>
  )
}

/** Print-only: every day's line, one after another, without map or controls. */
function PrintItinerary({ trip, weather, rainRisk }) {
  return (
    <div className="hidden print:block">
      {trip.days.map((day, i) => (
        <section key={day.date} className="mt-8 break-inside-avoid-page">
          <h2 className="border-b-[6px] pb-2 font-display wide text-2xl font-black" style={{ borderColor: lineColor(i) }}>
            Line {i + 1} · {day.label}
          </h2>
          <DayNotes note={trip.brief?.days?.find((d) => d.date === day.date)} source={trip.brief?.source} />
          <DayWarnings warnings={dayWarnings(day, weather[day.date], rainRisk[i])} />
          <div className="mt-3">
            <MetroLine day={day} color={lineColor(i)} base={trip.base} symbol={trip.city.symbol} onFocusStop={() => {}} />
          </div>
        </section>
      ))}
    </div>
  )
}
