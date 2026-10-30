import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { btn, btnPrimary, btnSignal, panel } from '../components/ui'
import { formatDateRange, humanize } from '../lib/format'
import { lineColor } from '../lib/lines'

function TripRow({ trip, index, onDelete }) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  async function remove() {
    setDeleting(true)
    setError('')
    try {
      await api.deleteTrip(trip.id)
      onDelete(trip.id)
    } catch (err) {
      setError(err.message)
      setDeleting(false)
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-4 py-4">
      <span className="grid size-10 shrink-0 place-items-center rounded-full border-[6px] bg-white font-display wide text-sm font-black" style={{ borderColor: lineColor(index) }} aria-hidden>
        {trip.days}
      </span>
      <div className="min-w-0 flex-1">
        <Link to={`/trips/${trip.id}`} className="font-display wide text-lg font-extrabold leading-tight hover:underline">
          {trip.title}
        </Link>
        <p className="font-mono text-xs text-steel">
          {humanize(trip.city)} · {trip.start_date ? formatDateRange(trip.start_date, trip.days) : `${trip.days} days`}
          {trip.updated_at && ` · updated ${new Date(trip.updated_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`}
        </p>
        {error && <p className="mt-1 text-sm text-[#B3261E]">{error}</p>}
      </div>
      {confirming ? (
        <div className="flex items-center gap-2" role="group" aria-label={`Confirm deleting ${trip.title}`}>
          <span className="text-sm">Delete this trip?</span>
          <button type="button" className={`${btn} border-[#B3261E] text-[#B3261E]`} onClick={remove} disabled={deleting}>
            {deleting ? 'Deleting…' : 'Yes, delete'}
          </button>
          <button type="button" className={btn} onClick={() => setConfirming(false)} disabled={deleting}>
            Keep it
          </button>
        </div>
      ) : (
        <div className="flex gap-2">
          <Link to={`/trips/${trip.id}`} className={btnPrimary}>
            Open
          </Link>
          <button type="button" className={btn} onClick={() => setConfirming(true)}>
            Delete
          </button>
        </div>
      )}
    </li>
  )
}

export default function MyTrips() {
  const { user, ready } = useAuth()
  const [trips, setTrips] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) return
    api
      .trips()
      .then(setTrips)
      .catch((err) => setError(err.message))
  }, [user])

  let body
  if (!ready) body = <p className="text-steel">Checking your account…</p>
  else if (!user) {
    body = (
      <div className={`${panel} p-6`}>
        <p className="font-semibold">Sign in to see the trips you’ve saved.</p>
        <Link to="/login?next=/trips" className={`${btnPrimary} mt-4`}>
          Sign in
        </Link>
      </div>
    )
  } else if (error) body = <p role="alert" className="text-[#B3261E]">{error}</p>
  else if (!trips) body = <p className="text-steel">Loading your trips…</p>
  else if (!trips.length) {
    body = (
      <div className={`${panel} p-6`}>
        <p className="font-display wide text-xl font-extrabold">No saved trips yet</p>
        <p className="mt-1 text-steel">Plan a few days somewhere, then press “Save trip” to keep it here and get a share link.</p>
        <Link to="/" className={`${btnSignal} mt-4`}>
          Plan a trip
        </Link>
      </div>
    )
  } else {
    body = (
      <ul className={`${panel} divide-y divide-rule px-4`}>
        {trips.map((t, i) => (
          <TripRow key={t.id} trip={t} index={i} onDelete={(id) => setTrips((list) => list.filter((x) => x.id !== id))} />
        ))}
      </ul>
    )
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-steel">Saved itineraries</p>
      <h1 className="mt-1 font-display wider text-4xl font-black tracking-tight sm:text-5xl">My trips</h1>
      <div className="mt-6">{body}</div>
    </main>
  )
}
