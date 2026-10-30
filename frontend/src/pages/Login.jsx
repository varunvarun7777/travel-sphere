import { useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import { btn, btnPrimary, fieldLabel, input, panel } from '../components/ui'

const DEMO = { email: 'demo@travelsphere.app', password: 'demo1234' }

// Only follow same-site paths after signing in.
const safeNext = (next) => (next && next.startsWith('/') && !next.startsWith('//') ? next : '/trips')

export default function Login() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))

  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (creating) await register({ name, email, password })
      else await login(email, password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-12 sm:px-6">
      <div className={`${panel} overflow-hidden`}>
        <div className="bg-ink px-5 py-4 text-white">
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-white/60">TravelSphere account</p>
          <h1 className="font-display wide text-2xl font-black">{creating ? 'Create an account' : 'Sign in'}</h1>
        </div>
        <form onSubmit={submit} className="space-y-4 p-5">
          {location.state?.reason === 'save' && (
            <p className="border-l-4 border-signal bg-white px-3 py-2 text-sm">Sign in to save your trip. Your draft is kept and waiting.</p>
          )}
          {creating && (
            <label className="block">
              <span className={fieldLabel}>Name</span>
              <input className={`${input} mt-1`} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
            </label>
          )}
          <label className="block">
            <span className={fieldLabel}>Email</span>
            <input className={`${input} mt-1`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
          </label>
          <label className="block">
            <span className={fieldLabel}>Password</span>
            <input
              className={`${input} mt-1`}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={creating ? 'new-password' : 'current-password'}
              minLength={creating ? 6 : undefined}
              required
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-[#B3261E]">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={btnPrimary} disabled={busy}>
              {busy ? 'One moment…' : creating ? 'Create account' : 'Sign in'}
            </button>
            {!creating && (
              <button
                type="button"
                className={btn}
                onClick={() => {
                  setEmail(DEMO.email)
                  setPassword(DEMO.password)
                }}
              >
                Use demo account
              </button>
            )}
          </div>
          <p className="border-t border-rule pt-4 text-sm text-steel">
            {creating ? 'Already have an account?' : 'New to TravelSphere?'}{' '}
            <button
              type="button"
              className="font-semibold text-ink underline"
              onClick={() => {
                setCreating(!creating)
                setError('')
              }}
            >
              {creating ? 'Sign in instead' : 'Create an account'}
            </button>
          </p>
        </form>
      </div>
    </main>
  )
}
