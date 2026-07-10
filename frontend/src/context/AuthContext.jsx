import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { api, setToken, getToken, setUnauthorizedHandler } from '../lib/api'

// Stan uwierzytelnienia: token w localStorage + dane zalogowanego użytkownika.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [uprawnienia, setUprawnienia] = useState([])
  const [uprawnieniaReady, setUprawnieniaReady] = useState(false)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    setUprawnienia([])
    setUprawnieniaReady(false)
  }, [])

  // Granularne uprawnienia (RBAC) — pobierane po zalogowaniu, do sterowania UI.
  useEffect(() => {
    if (!user) {
      setUprawnienia([])
      setUprawnieniaReady(false)
      return
    }
    if (Array.isArray(user.uprawnienia)) {
      setUprawnienia(user.uprawnienia)
      setUprawnieniaReady(true)
      return
    }

    setUprawnieniaReady(false)
    let off = false
    api('/me/uprawnienia')
      .then((r) => { if (!off) setUprawnienia(r.uprawnienia || []) })
      .catch(() => { if (!off) setUprawnienia([]) })
      .finally(() => { if (!off) setUprawnieniaReady(true) })
    return () => { off = true }
  }, [user])

  // Uprawnienia konta mogą zostać zmienione przez administratora w trakcie
  // otwartej sesji. Odświeżamy je po powrocie do aplikacji oraz okresowo,
  // bez migania ekranu stanem ładowania.
  useEffect(() => {
    if (!user) return undefined

    let off = false
    let inFlight = false
    const refreshUprawnienia = async () => {
      if (off || inFlight || document.visibilityState === 'hidden') return
      inFlight = true
      try {
        const response = await api('/me/uprawnienia')
        if (!off) setUprawnienia(response.uprawnienia || [])
      } catch {
        // Chwilowy błąd sieci nie powinien odbierać dostępu ani powodować
        // migania UI. Odpowiedź 401 nadal obsługuje globalny handler sesji.
      } finally {
        inFlight = false
      }
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refreshUprawnienia()
    }

    window.addEventListener('focus', refreshUprawnienia)
    document.addEventListener('visibilitychange', onVisibilityChange)
    const intervalId = window.setInterval(refreshUprawnienia, 60000)

    return () => {
      off = true
      window.removeEventListener('focus', refreshUprawnienia)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.clearInterval(intervalId)
    }
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
  const value = {
    user,
    loading,
    login,
    register,
    logout,
    isAdmin: user?.rola === 'admin',
    uprawnienia,
    uprawnieniaReady,
    can,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
