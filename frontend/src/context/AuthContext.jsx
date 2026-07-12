import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import {
  api,
  setToken,
  getToken,
  getPersistentToken,
  clearSessionToken,
  setUnauthorizedHandler,
  setWorkstationLockedHandler,
} from '../lib/api'
import {
  purgeReservationPrivacy,
  subscribeReservationPrivacyPurge,
} from '../lib/reservationPrivacy'
import { establishAuthenticatedSession } from '../lib/authTransition'

// Stan uwierzytelnienia: token w localStorage + dane zalogowanego użytkownika.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [uprawnienia, setUprawnienia] = useState([])
  const [uprawnieniaReady, setUprawnieniaReady] = useState(false)
  const [loading, setLoading] = useState(true)
  const [workstationLocked, setWorkstationLocked] = useState(false)
  const [workstationChecking, setWorkstationChecking] = useState(false)
  const [authorizationRefreshing, setAuthorizationRefreshing] = useState(false)
  const [authorizationError, setAuthorizationError] = useState(null)
  const workstationLockedRef = useRef(false)
  const workstationCheckingRef = useRef(false)
  const authGenerationRef = useRef(0)
  const authorizationRequestRef = useRef(0)
  const authorizationControllerRef = useRef(null)
  const authorizationBlockingRef = useRef(false)
  const userRef = useRef(user)
  userRef.current = user

  const applyAuthorizationSnapshot = useCallback((response) => {
    const permissions = response?.uprawnienia || []
    const current = userRef.current
    const nextRole = response?.rola || current?.rola
    if (current && nextRole && nextRole !== current.rola) {
      purgeReservationPrivacy({
        reason: 'authorization-change',
        preserveSafeRoute: true,
      })
    }
    setUprawnienia(permissions)
    setUser((previous) => {
      if (!previous) return previous
      const samePermissions = Array.isArray(previous.uprawnienia)
        && previous.uprawnienia.length === permissions.length
        && previous.uprawnienia.every((permission, index) => permission === permissions[index])
      if (previous.rola === nextRole && samePermissions) return previous
      const next = { ...previous, rola: nextRole, uprawnienia: permissions }
      userRef.current = next
      return next
    })
  }, [])

  const cancelAuthorizationRefresh = useCallback(() => {
    authorizationRequestRef.current += 1
    authorizationControllerRef.current?.abort()
    authorizationControllerRef.current = null
    authorizationBlockingRef.current = false
    setAuthorizationRefreshing(false)
    setAuthorizationError(null)
  }, [])

  const refreshAuthorizationSnapshot = useCallback(async ({ blocking = false, includeUser = false } = {}) => {
    const requestToken = getToken()
    const generation = authGenerationRef.current
    const requestId = authorizationRequestRef.current + 1
    const controller = new AbortController()
    authorizationRequestRef.current = requestId
    authorizationControllerRef.current?.abort()
    authorizationControllerRef.current = controller
    if (blocking) authorizationBlockingRef.current = true
    if (authorizationBlockingRef.current) {
      setAuthorizationRefreshing(true)
      setAuthorizationError(null)
      setUprawnieniaReady(false)
    }
    if (!requestToken) {
      if (authorizationBlockingRef.current) {
        setAuthorizationError('Brak aktywnej sesji do odświeżenia dostępu.')
      }
      return false
    }
    try {
      let nextUser = null
      let response = null
      if (includeUser) {
        nextUser = await api('/auth/me', 'GET', null, { signal: controller.signal })
        if (
          controller.signal.aborted
          || requestId !== authorizationRequestRef.current
          || generation !== authGenerationRef.current
          || getToken() !== requestToken
        ) return false
      }
      if (includeUser && Array.isArray(nextUser?.uprawnienia)) {
        response = nextUser
      } else {
        response = await api('/me/uprawnienia', 'GET', null, { signal: controller.signal })
      }
      if (
        controller.signal.aborted
        || requestId !== authorizationRequestRef.current
        || generation !== authGenerationRef.current
        || getToken() !== requestToken
      ) return false
      if (includeUser) {
        const permissions = response?.uprawnienia || []
        const refreshedUser = {
          ...nextUser,
          rola: response?.rola || nextUser?.rola,
          uprawnienia: permissions,
        }
        userRef.current = refreshedUser
        setUser(refreshedUser)
        setUprawnienia(permissions)
        setLoading(false)
      } else {
        applyAuthorizationSnapshot(response)
      }
      authorizationBlockingRef.current = false
      setAuthorizationRefreshing(false)
      setAuthorizationError(null)
      setUprawnieniaReady(true)
      return true
    } catch (error) {
      if (
        controller.signal.aborted
        || requestId !== authorizationRequestRef.current
        || generation !== authGenerationRef.current
        || getToken() !== requestToken
      ) return false
      if (authorizationBlockingRef.current) {
        setAuthorizationRefreshing(true)
        setAuthorizationError(error.message || 'Nie udało się odświeżyć uprawnień.')
      }
      if (includeUser) setLoading(false)
      return false
    } finally {
      if (authorizationControllerRef.current === controller) {
        authorizationControllerRef.current = null
      }
    }
  }, [applyAuthorizationSnapshot])

  const clearWorkstationLock = useCallback(() => {
    workstationLockedRef.current = false
    workstationCheckingRef.current = false
    setWorkstationLocked(false)
    setWorkstationChecking(false)
  }, [])

  const enterWorkstationLock = useCallback(({ purge = true } = {}) => {
    if (workstationLockedRef.current) return
    authGenerationRef.current += 1
    cancelAuthorizationRefresh()
    workstationLockedRef.current = true
    setWorkstationLocked(true)
    setLoading(false)
    setUprawnienia([])
    setUprawnieniaReady(false)
    if (purge) {
      purgeReservationPrivacy({
        reason: 'workstation-locked',
        preserveSafeRoute: true,
      })
    }
  }, [cancelAuthorizationRefresh])

  const logout = useCallback(() => {
    authGenerationRef.current += 1
    cancelAuthorizationRefresh()
    purgeReservationPrivacy({ reason: 'logout' })
    setToken(null)
    clearWorkstationLock()
    setUser(null)
    setUprawnienia([])
    setUprawnieniaReady(false)
    setLoading(false)
  }, [cancelAuthorizationRefresh, clearWorkstationLock])

  // Instalacja odbiornika cross-tab sprawia, że purge z innej karty czyści także
  // bieżący snapshot, nawet zanim przyszły ekran blokady stanowiska zostanie zamontowany.
  useEffect(() => {
    const unsubscribe = subscribeReservationPrivacyPurge((detail) => {
      if (detail?.reason === 'workstation-locked') {
        enterWorkstationLock({ purge: false })
        return
      }
      if (!detail?.external && detail?.reason === 'instance-change') {
        authGenerationRef.current += 1
        cancelAuthorizationRefresh()
        setToken(null)
        clearWorkstationLock()
        setUser(null)
        setUprawnienia([])
        setUprawnieniaReady(false)
        setLoading(false)
        return
      }
      if (!detail?.external) return

      if (detail.reason === 'authorization-change') {
        if (!getToken()) return
        authGenerationRef.current += 1
        workstationCheckingRef.current = false
        setWorkstationChecking(false)
        if (workstationLockedRef.current) return
        void refreshAuthorizationSnapshot({
          blocking: true,
          includeUser: !userRef.current,
        })
        return
      }

      if (['logout', 'unauthorized', 'instance-change'].includes(detail.reason)) {
        authGenerationRef.current += 1
        cancelAuthorizationRefresh()
        setToken(null)
        clearWorkstationLock()
        setUser(null)
        setUprawnienia([])
        setUprawnieniaReady(false)
        setLoading(false)
        return
      }
      if (detail.reason !== 'login') return

      const generation = ++authGenerationRef.current
      cancelAuthorizationRefresh()
      clearSessionToken()
      clearWorkstationLock()
      setUser(null)
      setUprawnienia([])
      setUprawnieniaReady(false)
      setLoading(true)
      const requestToken = getPersistentToken()
      if (!requestToken) {
        setLoading(false)
        return
      }
      api('/auth/me')
        .then((nextUser) => {
          if (generation === authGenerationRef.current && getToken() === requestToken) setUser(nextUser)
        })
        .catch(() => {})
        .finally(() => {
          if (generation === authGenerationRef.current && getToken() === requestToken) setLoading(false)
        })
    })
    return () => {
      authGenerationRef.current += 1
      unsubscribe()
    }
  }, [cancelAuthorizationRefresh, clearWorkstationLock, enterWorkstationLock, refreshAuthorizationSnapshot])

  // Granularne uprawnienia (RBAC) — pobierane po zalogowaniu, do sterowania UI.
  useEffect(() => {
    if (!user || workstationLocked) {
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
    refreshAuthorizationSnapshot({ blocking: false })
      .then((success) => { if (!off && !success) setUprawnienia([]) })
      .finally(() => { if (!off) setUprawnieniaReady(true) })
    return () => { off = true }
  }, [refreshAuthorizationSnapshot, user, workstationLocked])

  // Uprawnienia konta mogą zostać zmienione przez administratora w trakcie
  // otwartej sesji. Odświeżamy je po powrocie do aplikacji oraz okresowo,
  // bez migania ekranu stanem ładowania.
  useEffect(() => {
    if (!user || workstationLocked) return undefined

    let off = false
    let inFlight = false
    const refreshUprawnienia = async () => {
      if (off || inFlight || document.visibilityState === 'hidden') return
      inFlight = true
      try {
        await refreshAuthorizationSnapshot({ blocking: false })
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
  }, [refreshAuthorizationSnapshot, user, workstationLocked])

  // Reakcja na 401 z dowolnego zapytania + walidacja zapisanego tokenu na starcie.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      authGenerationRef.current += 1
      cancelAuthorizationRefresh()
      purgeReservationPrivacy({ reason: 'unauthorized' })
      clearWorkstationLock()
      setUser(null)
      setLoading(false)
    })
    setWorkstationLockedHandler(() => enterWorkstationLock())
    const clearSessionHandlers = () => {
      authGenerationRef.current += 1
      cancelAuthorizationRefresh()
      setUnauthorizedHandler(null)
      setWorkstationLockedHandler(null)
    }
    const t = getToken()
    if (!t) {
      setLoading(false)
      return clearSessionHandlers
    }
    const generation = authGenerationRef.current
    api('/auth/me')
      .then((nextUser) => {
        if (generation === authGenerationRef.current && getToken() === t) {
          setUser(nextUser)
          setLoading(false)
        }
      })
      .catch((error) => {
        // 423 blokuje jedynie stanowisko. Token pozostaje potrzebny do przyszłej
        // reautoryzacji PIN-em; pozostałe błędy zachowują dotychczasowy fallback.
        if (generation !== authGenerationRef.current || getToken() !== t) return
        if (error?.status !== 423) setToken(null)
        setLoading(false)
      })
    return clearSessionHandlers
  }, [cancelAuthorizationRefresh, clearWorkstationLock, enterWorkstationLock])

  const retryWorkstation = useCallback(async () => {
    if (workstationCheckingRef.current) return false
    workstationCheckingRef.current = true
    setWorkstationChecking(true)
    const generation = authGenerationRef.current
    const requestToken = getToken()
    try {
      const nextUser = await api('/auth/me')
      if (generation !== authGenerationRef.current || getToken() !== requestToken) return false
      cancelAuthorizationRefresh()
      clearWorkstationLock()
      setUser(nextUser)
      return true
    } catch (error) {
      if (generation !== authGenerationRef.current || getToken() !== requestToken) return false
      if (error?.status === 423 && error?.code === 'WORKSTATION_LOCKED') return false
      throw error
    } finally {
      if (generation === authGenerationRef.current && getToken() === requestToken) {
        workstationCheckingRef.current = false
        setWorkstationChecking(false)
      }
    }
  }, [cancelAuthorizationRefresh, clearWorkstationLock])

  const retryAuthorization = useCallback(
    () => refreshAuthorizationSnapshot({
      blocking: true,
      includeUser: !userRef.current,
    }),
    [refreshAuthorizationSnapshot],
  )

  // Logowanie e-mailem (nowe konta). Fallback: gdy identyfikator nie wygląda na e-mail
  // (brak „@") — np. deweloperskie/legacy konto po loginie — wysyłamy go jako `login`.
  const login = useCallback(async (identyfikator, haslo, remember = true) => {
    const generation = ++authGenerationRef.current
    const ident = (identyfikator || '').trim()
    const body = ident.includes('@') ? { email: ident, haslo } : { login: ident, haslo }
    const res = await api('/auth/login', 'POST', body)
    if (generation !== authGenerationRef.current) {
      const error = new Error('Ta próba logowania została zastąpiona nowszą zmianą sesji.')
      error.code = 'AUTH_TRANSITION_SUPERSEDED'
      throw error
    }
    establishAuthenticatedSession(res.access_token, remember)
    cancelAuthorizationRefresh()
    clearWorkstationLock()
    setUser(res.user)
    return res.user
  }, [cancelAuthorizationRefresh, clearWorkstationLock])

  // Rejestracja pracownika — po sukcesie od razu loguje (backend zwraca token).
  const register = useCallback(async (dane) => {
    const generation = ++authGenerationRef.current
    const res = await api('/auth/register', 'POST', dane)
    if (generation !== authGenerationRef.current) {
      const error = new Error('Ta próba rejestracji została zastąpiona nowszą zmianą sesji.')
      error.code = 'AUTH_TRANSITION_SUPERSEDED'
      throw error
    }
    establishAuthenticatedSession(res.access_token)
    cancelAuthorizationRefresh()
    clearWorkstationLock()
    setUser(res.user)
    return res.user
  }, [cancelAuthorizationRefresh, clearWorkstationLock])

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
    workstationLocked,
    workstationChecking,
    retryWorkstation,
    authorizationRefreshing,
    authorizationError,
    retryAuthorization,
    can,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
