import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { api, setToken, getToken, setUnauthorizedHandler } from '../lib/api'

// Stan uwierzytelnienia: token w localStorage + dane zalogowanego użytkownika.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [uprawnienia, setUprawnienia] = useState([])
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    setUprawnienia([])
  }, [])

  // Granularne uprawnienia (RBAC) — pobierane po zalogowaniu, do sterowania UI.
  useEffect(() => {
    if (!user) { setUprawnienia([]); return }
    let off = false
    api('/me/uprawnienia')
      .then((r) => { if (!off) setUprawnienia(r.uprawnienia || []) })
      .catch(() => { if (!off) setUprawnienia([]) })
    return () => { off = true }
  }, [user])

  // Reakcja na 401 z dowolnego zapytania + walidacja zapisanego tokenu na starcie.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
    const t = getToken()
    if (!t) {
      setLoading(false)
      return
    }
    api('/auth/me')
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  // Logowanie e-mailem (nowe konta). Fallback: gdy identyfikator nie wygląda na e-mail
  // (brak „@") — np. deweloperskie/legacy konto po loginie — wysyłamy go jako `login`.
  const login = useCallback(async (identyfikator, haslo, remember = true) => {
    const ident = (identyfikator || '').trim()
    const body = ident.includes('@') ? { email: ident, haslo } : { login: ident, haslo }
    const res = await api('/auth/login', 'POST', body)
    setToken(res.access_token, remember)
    setUser(res.user)
    return res.user
  }, [])

  // Rejestracja pracownika — po sukcesie od razu loguje (backend zwraca token).
  const register = useCallback(async (dane) => {
    const res = await api('/auth/register', 'POST', dane)
    setToken(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const can = useCallback((perm) => uprawnienia.includes(perm), [uprawnienia])
  const value = { user, loading, login, register, logout, isAdmin: user?.rola === 'admin', uprawnienia, can }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
