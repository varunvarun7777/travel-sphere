import { useState } from 'react'
import { api } from '../api'
import { btn, input } from './ui'

/** "Where you're staying": geocode search scoped to the city; null means the city centre. */
export default function LocationSearch({ city, value, onChange }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function search() {
    const q = query.trim()
    if (!q) return
    setBusy(true)
    setError('')
    try {
      const found = await api.geocode(q, city.id)
      setResults(found)
      if (!found.length) setError(`No matches for “${q}” in ${city.name}. Try your hotel’s name or street.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span aria-hidden className="size-3 bg-ink" />
        <span className="font-semibold">{value ? value.name : `${city.name} centre`}</span>
        {value && (
          <button type="button" className="text-steel underline hover:text-ink" onClick={() => onChange(null)}>
            Use city centre instead
          </button>
        )}
      </p>
      <div className="mt-2 flex gap-2">
        <input
          className={input}
          aria-label="Search for where you're staying"
          placeholder="Hotel, street or neighbourhood"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              search()
            }
          }}
        />
        <button type="button" className={btn} onClick={search} disabled={busy || !query.trim()}>
          {busy ? 'Finding…' : 'Find'}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-[#B3261E]">{error}</p>}
      {results.length > 0 && (
        <ul className="mt-2 divide-y divide-rule rounded-md border border-rule bg-white">
          {results.map((r) => (
            <li key={`${r.name}-${r.lat}-${r.lng}`}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left text-sm hover:bg-concrete"
                onClick={() => {
                  onChange(r)
                  setResults([])
                  setQuery('')
                }}
              >
                {r.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
