import { Link, Route, Routes } from 'react-router-dom'
import TopBar from './components/TopBar'
import { btnPrimary } from './components/ui'
import Login from './pages/Login'
import MyTrips from './pages/MyTrips'
import Planner from './pages/Planner'
import TripPage from './pages/Trip'

function NotFound() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-steel">Error 404</p>
      <h1 className="mt-1 font-display wider text-4xl font-black">This stop isn’t on the line</h1>
      <p className="mt-2 text-steel">The page you asked for doesn’t exist. Check the link, or start a new plan.</p>
      <Link to="/" className={`${btnPrimary} mt-5`}>
        Plan my days
      </Link>
    </main>
  )
}

export default function App() {
  return (
    <div className="min-h-screen">
      <TopBar />
      <Routes>
        <Route path="/" element={<Planner />} />
        <Route path="/trip" element={<TripPage mode="draft" />} />
        <Route path="/trips" element={<MyTrips />} />
        <Route path="/trips/:id" element={<TripPage mode="saved" />} />
        <Route path="/s/:slug" element={<TripPage mode="shared" />} />
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  )
}
