// Holds the logged-in user (or null) and auth actions, so any page can
// read `useAuth()` instead of re-implementing token handling. Mirrors the
// existing AnalysisContext pattern in this codebase.
//
// Phase 1 change: there's no token in localStorage to check on mount
// anymore (see api.js). Instead, on load, silently try to exchange the
// httpOnly refresh cookie (if any) for a fresh access token — this is
// what makes a page refresh not immediately log the user out even though
// the access token itself only lives in memory.
import { createContext, useContext, useState, useEffect } from 'react'
import {
  getMe, loginUser, registerUser, logoutUser, refreshSession,
  setAccessToken, clearAccessToken, setCsrfToken, clearCsrfToken,
} from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    refreshSession()
      .then((res) => {
        setAccessToken(res.data.access_token)
        setCsrfToken(res.data.csrf_token)
        return getMe()
      })
      .then((res) => setUser(res.data))
      .catch(() => { clearAccessToken(); clearCsrfToken() })
      .finally(() => setLoading(false))
  }, [])

  const login = async (email, password) => {
    const res = await loginUser(email, password)
    setAccessToken(res.data.access_token)
    setCsrfToken(res.data.csrf_token)
    const me = await getMe()
    setUser(me.data)
    return me.data
  }

  const register = async (payload) => {
    const res = await registerUser(payload)
    setAccessToken(res.data.access_token)
    setCsrfToken(res.data.csrf_token)
    const me = await getMe()
    setUser(me.data)
    return me.data
  }

  const logout = async () => {
    try {
      await logoutUser()
    } finally {
      clearAccessToken()
      clearCsrfToken()
      setUser(null)
    }
  }

  const refreshUser = async () => {
    const me = await getMe()
    setUser(me.data)
    return me.data
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
