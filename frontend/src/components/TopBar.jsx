import { useEffect, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'

function navClass({ isActive }) {
  return `relative px-3 py-4 text-sm font-semibold ${
    isActive ? 'text-white after:absolute after:inset-x-3 after:bottom-0 after:h-1 after:bg-signal' : 'text-white/70 hover:text-white'
  }`
}

const PROVIDER_LABEL = { gemini: 'Gemini', claude: 'Claude', rules: 'keyword rules' }

function AiStatus() {
  const [status, setStatus] = useState(null)
  useEffect(() => {
    api
      .aiStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
  }, [])
  if (!status) return null
  const live = status.provider !== 'rules'
  const label = PROVIDER_LABEL[status.provider] || status.provider
  return (
    <span
      className="hidden items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-white/60 md:inline-flex"
      title={live ? `Requests are read by ${label} (${status.model})` : 'No AI key is configured; TravelSphere reads requests with keyword rules'}
    >
      <span className={`size-2 rounded-full ${live ? 'bg-signal' : 'bg-white/40'}`} aria-hidden />
      AI: {label}
    </span>
  )
}

export default function TopBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <header className="bg-ink text-white print:hidden">
      <div className="mx-auto flex max-w-[1440px] items-center gap-4 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5 py-3" aria-label="TravelSphere home">
          <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden>
            <circle cx="13" cy="13" r="10" fill="none" stroke="#fff" strokeWidth="4" />
            <circle cx="13" cy="13" r="4" fill="#FFC20E" />
          </svg>
          <span className="font-display wide text-xl font-black tracking-tight">TravelSphere</span>
        </Link>
        <div className="ml-auto flex items-center gap-4">
          <AiStatus />
          <nav aria-label="Main" className="flex items-center">
            <NavLink to="/" end className={navClass}>
              Plan
            </NavLink>
            <NavLink to="/trips" className={navClass}>
              My trips
            </NavLink>
            {user ? (
              <button
                type="button"
                onClick={() => {
                  logout()
                  navigate('/')
                }}
                className="px-3 py-4 text-sm font-semibold text-white/70 hover:text-white"
                title={`Signed in as ${user.email}`}
              >
                Sign out
              </button>
            ) : (
              <NavLink to="/login" className={navClass}>
                Sign in
              </NavLink>
            )}
          </nav>
        </div>
      </div>
    </header>
  )
}
