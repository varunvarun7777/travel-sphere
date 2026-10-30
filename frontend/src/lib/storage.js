// Browser storage can throw (private mode, blocked site data), so every access is guarded.
function attempt(fn, fallback = null) {
  try {
    return fn()
  } catch {
    return fallback
  }
}

function wrap(getStore) {
  return {
    get: (key) => attempt(() => getStore().getItem(key)),
    set: (key, value) => attempt(() => getStore().setItem(key, value)),
    remove: (key) => attempt(() => getStore().removeItem(key)),
  }
}

export const local = wrap(() => window.localStorage)
export const session = wrap(() => window.sessionStorage)

export function readJSON(store, key) {
  const raw = store.get(key)
  return raw ? attempt(() => JSON.parse(raw)) : null
}

export function writeJSON(store, key, value) {
  store.set(key, JSON.stringify(value))
}
