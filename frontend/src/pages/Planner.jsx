import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import CityMap from '../components/CityMap'
import LocationSearch from '../components/LocationSearch'
import PlacePicker from '../components/PlacePicker'
import { btn, btnSignal, fieldLabel, input, panel, segment } from '../components/ui'
import { addDays, humanize, toISODate } from '../lib/format'
import { INTERESTS, MODES, PACES } from '../lib/lines'
import { writeDraft } from '../lib/trip'

const today = () => toISODate(new Date())

const initialForm = () => ({
  city: '',
  start_date: addDays(today(), 7),
  days: 3,
  pace: 'balanced',
  mode: 'auto',
  interests: [],
  must_see: [],
  avoid: [],
  base: null,
})

const PARSE_SOURCE = { gemini: 'Read by Gemini', claude: 'Read by Claude', rules: 'Read by keyword rules' }

// The parser may return place ids or names; map both onto ids of the loaded places.
function resolvePlaceRefs(refs, places) {
  const ids = refs
    .map((ref) => {
      const r = String(ref).toLowerCase()
      return places.find((p) => p.id === ref || p.name.toLowerCase() === r)?.id
    })
    .filter(Boolean)
  return [...new Set(ids)]
}

function Section({ number, title, children }) {
  return (
    <section className="border-t border-rule pt-5">
      <h2 className="flex items-center gap-3 font-display wide text-lg font-extrabold">
        <span className="grid size-7 place-items-center rounded-full bg-ink font-mono text-xs font-semibold text-white">{number}</span>
        {title}
      </h2>
      <div className="mt-4 space-y-5">{children}</div>
    </section>
  )
}

function Field({ label, filled, children, as: Tag = 'div' }) {
  return (
    <Tag className="block">
      <span className="flex items-center gap-2">
        <span className={fieldLabel}>{label}</span>
        {filled && <span className="rounded-sm bg-signal px-1.5 text-[11px] font-semibold">From your note</span>}
      </span>
      <span className="mt-1.5 block">{children}</span>
    </Tag>
  )
}

function BuildingNotice({ name }) {
  return (
    <p className="mt-3 border-l-4 border-signal bg-white px-3 py-2 text-sm" role="status">
      Building a guide to <b>{name}</b>: Gemini lists the sights, then the city is checked against the map and far-off results are dropped. This takes
      about 20–40 seconds, and only happens once per city.
    </p>
  )
}

export default function Planner() {
  const navigate = useNavigate()
  const [cities, setCities] = useState([])
  const [places, setPlaces] = useState([])
  const [form, setForm] = useState(initialForm)
  const [filled, setFilled] = useState(new Set())
  const [loadError, setLoadError] = useState('')

  const [text, setText] = useState('')
  const [parsing, setParsing] = useState(false)
  const [parsed, setParsed] = useState(null)
  const [parseError, setParseError] = useState('')

  const [building, setBuilding] = useState(null)
  const [newCity, setNewCity] = useState('')
  const [cityError, setCityError] = useState('')

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  useEffect(() => {
    api
      .cities()
      .then((list) => {
        setCities(list)
        setForm((f) => (f.city ? f : { ...f, city: list[0]?.id ?? '' }))
      })
      .catch((err) => setLoadError(err.message))
  }, [])

  useEffect(() => {
    if (!form.city) return
    let cancelled = false
    setPlaces([])
    api
      .places(form.city)
      .then((list) => {
        if (cancelled) return
        setPlaces(list)
        setForm((f) => ({ ...f, must_see: resolvePlaceRefs(f.must_see, list), avoid: resolvePlaceRefs(f.avoid, list) }))
      })
      .catch((err) => !cancelled && setLoadError(err.message))
    return () => {
      cancelled = true
    }
  }, [form.city])

  const city = cities.find((c) => c.id === form.city)

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }))
    setFilled((s) => {
      if (!s.has(field)) return s
      const next = new Set(s)
      next.delete(field)
      return next
    })
  }

  function changeCity(id) {
    setForm((f) => ({ ...f, city: id, must_see: [], avoid: [], base: null }))
    setFilled(new Set())
  }

  function setPlaceState(id, state) {
    setForm((f) => ({
      ...f,
      must_see: state === 'must' ? [...f.must_see.filter((x) => x !== id), id] : f.must_see.filter((x) => x !== id),
      avoid: state === 'avoid' ? [...f.avoid.filter((x) => x !== id), id] : f.avoid.filter((x) => x !== id),
    }))
  }

  const stateOf = (id) => (form.must_see.includes(id) ? 'must' : form.avoid.includes(id) ? 'avoid' : 'none')
  const cycle = (id) => setPlaceState(id, { none: 'must', must: 'avoid', avoid: 'none' }[stateOf(id)])

  // Builds a guide for a city TravelSphere doesn't know yet, then reloads the city list.
  async function addCity(name) {
    setBuilding(name)
    try {
      const { city } = await api.discoverCity(name)
      const list = await api.cities()
      setCities(list)
      return { city, list }
    } finally {
      setBuilding(null)
    }
  }

  async function addCityFromBox(e) {
    e.preventDefault()
    setCityError('')
    try {
      const { city } = await addCity(newCity.trim())
      setNewCity('')
      changeCity(city.id)
    } catch (err) {
      setCityError(err.message)
    }
  }

  async function readRequest() {
    setParsing(true)
    setParseError('')
    setParsed(null)
    try {
      let { source, prefs } = await api.parse(text)
      let knownCities = cities
      if (prefs.new_city) {
        knownCities = (await addCity(prefs.new_city)).list
        // Read again now the city's places exist, so must-see and skip can be matched.
        ;({ source, prefs } = await api.parse(text))
      }
      const next = { ...form }
      const changed = []
      const mark = (field, label, value) => {
        changed.push({ field, label, value })
      }

      if (prefs.city) {
        const key = prefs.city.toLowerCase()
        const match = knownCities.find((c) => c.id === key || c.name.toLowerCase() === key)
        if (match && match.id !== form.city) {
          Object.assign(next, { city: match.id, must_see: [], avoid: [], base: null })
          mark('city', 'City', match.name)
        }
      }
      if (prefs.days) {
        next.days = Math.min(7, Math.max(1, prefs.days))
        if (next.days !== form.days) mark('days', 'Days', String(next.days))
      }
      if (prefs.start_date && prefs.start_date !== form.start_date) {
        next.start_date = prefs.start_date
        mark('start_date', 'Start date', prefs.start_date)
      }
      if (prefs.pace && prefs.pace !== form.pace) {
        next.pace = prefs.pace
        mark('pace', 'Pace', humanize(prefs.pace))
      }
      if (prefs.mode && prefs.mode !== form.mode) {
        next.mode = prefs.mode
        mark('mode', 'Getting around', humanize(prefs.mode))
      }
      if (prefs.interests?.length) {
        next.interests = prefs.interests.filter((i) => INTERESTS.includes(i))
        mark('interests', 'Interests', next.interests.join(', '))
      }
      const sameCity = next.city === form.city
      if (prefs.must_see?.length) {
        next.must_see = sameCity ? resolvePlaceRefs(prefs.must_see, places) : prefs.must_see
        mark('places', 'Must see', prefs.must_see.length)
      }
      if (prefs.avoid?.length) {
        next.avoid = sameCity ? resolvePlaceRefs(prefs.avoid, places) : prefs.avoid
        mark('places', 'Skip', prefs.avoid.length)
      }

      setForm(next)
      setFilled(new Set(changed.map((c) => c.field)))
      setParsed({ source, changed, prefs })
    } catch (err) {
      setParseError(err.message)
    } finally {
      setParsing(false)
    }
  }

  function describeChange(c) {
    if (c.label === 'Must see' || c.label === 'Skip') {
      const refs = c.label === 'Must see' ? parsed.prefs.must_see : parsed.prefs.avoid
      return refs.map((r) => places.find((p) => p.id === r || p.name.toLowerCase() === String(r).toLowerCase())?.name ?? humanize(r)).join(', ')
    }
    return c.value
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.city || !form.start_date) {
      setSubmitError('Pick a city and a start date, then try again.')
      return
    }
    setSubmitting(true)
    setSubmitError('')
    try {
      const trip = await api.plan({
        city: form.city,
        start_date: form.start_date,
        days: form.days,
        pace: form.pace,
        mode: form.mode,
        interests: form.interests,
        must_see: form.must_see,
        avoid: form.avoid,
        base: form.base ? { name: form.base.name, lat: form.base.lat, lng: form.base.lng } : null,
        custom_places: [],
      })
      writeDraft({ trip })
      navigate('/trip')
    } catch (err) {
      setSubmitError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <main className="mx-auto grid max-w-[1440px] gap-8 px-4 pb-16 pt-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-10">
      <div className="min-w-0">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-steel">Daily sightseeing planner</p>
        <h1 className="mt-2 font-display wider text-[2.6rem] font-black leading-[0.92] tracking-tight sm:text-6xl">
          Your trip,
          <br />
          drawn as a metro map.
        </h1>
        <p className="mt-4 max-w-xl text-steel">
          Each day becomes a line. TravelSphere picks the places you’ll care about, puts them in the shortest order and times every stop around
          opening hours, lunch and sunset.
        </p>

        {loadError && (
          <p role="alert" className="mt-5 rounded-md border border-[#B3261E] bg-white px-4 py-3 text-sm text-[#B3261E]">
            {loadError}
          </p>
        )}

        <div className={`${panel} mt-6 p-4`}>
          <label htmlFor="trip-request" className="font-display wide text-lg font-extrabold">
            Describe your trip
          </label>
          <p className="text-sm text-steel">Write it the way you’d tell a friend. TravelSphere fills in the form below; you can change anything after.</p>
          <textarea
            id="trip-request"
            rows={3}
            className={`${input} mt-3 resize-y`}
            placeholder="3 relaxed days in Rome from 12 May, love art and food, must see the Colosseum, skip the Vatican"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button type="button" className={btn} onClick={readRequest} disabled={parsing || !text.trim()}>
              {building ? 'Building city guide…' : parsing ? 'Reading…' : 'Read my request'}
            </button>
            {parseError && <p className="text-sm text-[#B3261E]">{parseError}</p>}
          </div>
          {building && <BuildingNotice name={building} />}
          {parsed && (
            <div className="mt-4 border-l-4 border-signal bg-white px-3 py-2" role="status">
              <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-steel">{PARSE_SOURCE[parsed.source] || PARSE_SOURCE.rules}</p>
              {parsed.changed.length ? (
                <ul className="mt-1 space-y-0.5 text-sm">
                  {parsed.changed.map((c) => (
                    <li key={c.label}>
                      <span className="font-semibold">{c.label}:</span> {describeChange(c)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm">Nothing new to fill in. Try naming a city, a number of days, a start date or what you like.</p>
              )}
            </div>
          )}
        </div>

        <form onSubmit={submit} className="mt-6 space-y-6">
          <Section number="1" title="Where and when">
            <Field label="City" filled={filled.has('city')}>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="City">
                {cities.map((c) => (
                  <button key={c.id} type="button" role="radio" aria-checked={form.city === c.id} onClick={() => changeCity(c.id)} className={segment(form.city === c.id)}>
                    <span className="block font-display wide font-extrabold">{c.name}</span>
                    <span className={`block text-xs ${form.city === c.id ? 'text-white/70' : 'text-steel'}`}>
                      {c.country}
                      {c.generated && ' · AI guide'}
                    </span>
                  </button>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  className={`${input} max-w-xs`}
                  placeholder="Another city, e.g. Bengaluru"
                  aria-label="Add another city"
                  value={newCity}
                  onChange={(e) => setNewCity(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addCityFromBox(e)}
                  disabled={Boolean(building)}
                />
                <button type="button" className={btn} onClick={addCityFromBox} disabled={Boolean(building) || newCity.trim().length < 2}>
                  {building && !parsing ? 'Building guide…' : 'Add city'}
                </button>
                {cityError && <p className="w-full text-sm text-[#B3261E]">{cityError}</p>}
              </div>
              {building && !parsing && <BuildingNotice name={building} />}
            </Field>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field as="label" label="Start date" filled={filled.has('start_date')}>
                <input type="date" className={`${input} font-mono`} min={today()} value={form.start_date} onChange={(e) => update('start_date', e.target.value)} required />
              </Field>
              <Field label="Days" filled={filled.has('days')}>
                <div className="flex items-center gap-2">
                  <button type="button" className={`${btn} w-10`} onClick={() => update('days', Math.max(1, form.days - 1))} disabled={form.days <= 1} aria-label="One day fewer">
                    −
                  </button>
                  <output className="w-12 text-center font-mono text-xl font-semibold" aria-live="polite">
                    {form.days}
                  </output>
                  <button type="button" className={`${btn} w-10`} onClick={() => update('days', Math.min(7, form.days + 1))} disabled={form.days >= 7} aria-label="One day more">
                    +
                  </button>
                  <span className="text-sm text-steel">1 to 7</span>
                </div>
              </Field>
            </div>
            {city && (
              <Field label="Where you’re staying">
                <LocationSearch key={city.id} city={city} value={form.base} onChange={(base) => update('base', base)} />
              </Field>
            )}
          </Section>

          <Section number="2" title="How you like to travel">
            <Field label="Pace" filled={filled.has('pace')}>
              <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Pace">
                {PACES.map((p) => (
                  <button key={p.id} type="button" role="radio" aria-checked={form.pace === p.id} onClick={() => update('pace', p.id)} className={segment(form.pace === p.id)}>
                    <span className="block font-semibold">{p.label}</span>
                    <span className={`block font-mono text-[11px] ${form.pace === p.id ? 'text-white/70' : 'text-steel'}`}>{p.hours}</span>
                    <span className={`block text-xs ${form.pace === p.id ? 'text-white/70' : 'text-steel'}`}>{p.hint}</span>
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Getting around" filled={filled.has('mode')}>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Getting around">
                {MODES.map((m) => (
                  <button key={m.id} type="button" role="radio" aria-checked={form.mode === m.id} onClick={() => update('mode', m.id)} className={segment(form.mode === m.id)}>
                    <span className="block font-semibold">{m.label}</span>
                    <span className={`block text-xs ${form.mode === m.id ? 'text-white/70' : 'text-steel'}`}>{m.hint}</span>
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Interests" filled={filled.has('interests')}>
              <div className="flex flex-wrap gap-2">
                {INTERESTS.map((i) => {
                  const on = form.interests.includes(i)
                  return (
                    <button
                      key={i}
                      type="button"
                      aria-pressed={on}
                      onClick={() => update('interests', on ? form.interests.filter((x) => x !== i) : [...form.interests, i])}
                      className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold ${on ? 'border-ink bg-ink text-white' : 'border-rule bg-white hover:border-ink'}`}
                    >
                      {humanize(i)}
                    </button>
                  )
                })}
              </div>
            </Field>
          </Section>

          <Section number="3" title="Places to include or skip">
            <Field label="Places" filled={filled.has('places')}>
              <PlacePicker places={places} mustSee={form.must_see} avoid={form.avoid} onSet={setPlaceState} />
            </Field>
          </Section>

          <div className="border-t border-rule pt-5">
            {submitError && (
              <p role="alert" className="mb-3 text-sm text-[#B3261E]">
                {submitError}
              </p>
            )}
            <button type="submit" className={`${btnSignal} w-full sm:w-auto`} disabled={submitting || !form.city}>
              {submitting ? 'Planning your days…' : 'Plan my days'}
            </button>
            <p className="mt-2 text-sm text-steel">You can reorder, add and remove stops on the next screen.</p>
          </div>
        </form>
      </div>

      <aside className="min-w-0 lg:sticky lg:top-4 lg:self-start" aria-label="City map">
        <div className="h-[55vh] min-h-[320px] overflow-hidden rounded-md border border-rule bg-panel lg:h-[calc(100vh-7rem)]">
          {city ? <CityMap city={city} places={places} stateOf={stateOf} onCycle={cycle} base={form.base} /> : null}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-steel">
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-3 rounded-full border-2 border-steel bg-white" /> Place
          </span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-4 rounded-full border-2 border-ink bg-signal" /> Must see ({form.must_see.length})
          </span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-3 rounded-full border border-ink bg-ink/35" /> Skip ({form.avoid.length})
          </span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-3 bg-ink" /> Base
          </span>
          <span className="w-full text-xs">Click a dot to cycle: must see → skip → clear.</span>
        </div>
      </aside>
    </main>
  )
}
