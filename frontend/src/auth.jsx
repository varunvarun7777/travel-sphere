import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api, tokenStore } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(() => !tokenStore.get())

  useEffect(() => {
    if (!tokenStore.get()) return
    api
      .me()
      .then(setUser)
      .catch((err) => {
        if (err.status === 401) tokenStore.clear()
      })
      .finally(() => setReady(true))
  }, [])

  const value = useMemo(() => {
    const accept = (res) => {
      tokenStore.set(res.access_token)
      setUser(res.user)
      return res.user
    }
    return {
      user,
      ready,
      login: async (email, password) => accept(await api.login(email, password)),
      register: async (details) => accept(await api.register(details)),
      logout: () => {
        tokenStore.clear()
        setUser(null)
      },
    }
  }, [user, ready])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
