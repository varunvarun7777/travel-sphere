import { local } from './lib/storage'

const TOKEN_KEY = 'travelsphere.token'

export const tokenStore = {
  get: () => local.get(TOKEN_KEY),
  set: (token) => local.set(TOKEN_KEY, token),
  clear: () => local.remove(TOKEN_KEY),
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function errorMessage(data, status) {
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) return detail.map((d) => d.msg).filter(Boolean).join('; ')
  if (status === 401) return 'Your session has expired. Sign in again to continue.'
  if (status === 404) return 'That could not be found. It may have been deleted.'
  return `The server hit a problem (error ${status}). Try again in a moment.`
}

async function request(path, { method = 'GET', json, form, blob = false } = {}) {
  const headers = {}
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`

  let body
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = new URLSearchParams(form)
  } else if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  }

  let res
  try {
    res = await fetch(`/api${path}`, { method, headers, body })
  } catch {
    throw new ApiError("Can't reach the TravelSphere server. Check that the backend is running on port 8000, then try again.", 0)
  }
  if (blob && res.ok) return res.blob()
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status)
  return data
}

const post = (path, json) => request(path, { method: 'POST', json })

export const api = {
  cities: () => request('/cities'),
  discoverCity: (name) => post('/cities/discover', { name }),
  places: (cityId) => request(`/cities/${encodeURIComponent(cityId)}/places`),
  geocode: (q, city) => request(`/geocode?${new URLSearchParams({ q, city })}`),

  plan: (body) => post('/plan', body),
  schedule: (body) => post('/schedule', body),

  aiStatus: () => request('/ai/status'),
  parse: (text) => post('/ai/parse', { text }),
  brief: (trip) => post('/ai/brief', { trip }),
  pdf: (trip) => request('/export/pdf', { method: 'POST', json: { trip }, blob: true }),

  register: (body) => post('/auth/register', body),
  login: (email, password) => request('/auth/login', { method: 'POST', form: { username: email, password } }),
  me: () => request('/auth/me'),

  trips: () => request('/trips'),
  trip: (id) => request(`/trips/${encodeURIComponent(id)}`),
  createTrip: (title, data) => post('/trips', { title, data }),
  updateTrip: (id, title, data) => request(`/trips/${encodeURIComponent(id)}`, { method: 'PUT', json: { title, data } }),
  deleteTrip: (id) => request(`/trips/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  sharedTrip: (slug) => request(`/share/${encodeURIComponent(slug)}`),
}
