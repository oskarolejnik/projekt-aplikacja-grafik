import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import {
  api,
  setToken,
  getToken,
  getPersistentToken,
  clearSessionToken,
  clearWorkstationCsrf,
  getWorkstationCsrf,
  rotateCredentialGeneration,
  setUnauthorizedHandler,
  setWorkstationLockedHandler,
} from '../lib/api'
import {
  purgeReservationPrivacy,
  subscribeReservationPrivacyPurge,
} from '../lib/reservationPrivacy'
import { establishAuthenticatedSession } from '../lib/authTransition'
import {
  clearWorkstationReservationContexts,
  rememberWorkstationReservationContext,
  restoreWorkstationReservationContext,
} from '../lib/workstationContext'
import { reservationHistoryState } from '../lib/reservationSession'

// Stan uwierzytelnienia: token w localStorage + dane zalogowanego użytkownika.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [uprawnienia, setUprawnienia] = useState([])
  const [uprawnieniaReady, setUprawnieniaReady] = useState(false)
  const [loading, setLoading] = useState(true)
  const [workstationLocked, setWorkstationLocked] = useState(false)
  const [workstationChecking, setWorkstationChecking] = useState(false)
  const [workstationGate, setWorkstationGate] = useState(null)
  const [workstationSession, setWorkstationSession] = useState(null)
  const [workstationIdleWarning, setWorkstationIdleWarning] = useState(null)
  const [workstationVersion, setWorkstationVersion] = useState(0)
  const [authorizationRefreshing, setAuthorizationRefreshing] = useState(false)
  const [authorizationError, setAuthorizationError] = useState(null)
  const workstationLockedRef = useRef(false)
  const workstationCheckingRef = useRef(false)
  const authGenerationRef = useRef(0)
  const authorizationRequestRef = useRef(0)
  const authorizationControllerRef = useRef(null)
  const authorizationBlockingRef = useRef(false)
  const userRef = useRef(user)
  const workstationGateRef = useRef(workstationGate)
  const workstationSessionRef = useRef(workstationSession)
  userRef.current = user
  workstationGateRef.current = workstationGate
  workstationSessionRef.current = workstationSession

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
    const requestWorkstation = workstationSessionRef.current?.active
      ? `${workstationSessionRef.current.station?.id || ''}:${workstationSessionRef.current.user?.id || ''}`
      : null
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
    if (!requestToken && !requestWorkstation) {
      if (authorizationBlockingRef.current) {
        setAuthorizationError('Brak aktywnej sesji do odświeżenia dostępu.')
      }
      return false
    }
    const credentialStillCurrent = () => {
      if (generation !== authGenerationRef.current) return false
      if (requestToken) return getToken() === requestToken
      const current = workstationSessionRef.current
      return !getToken()
        && current?.active
        && `${current.station?.id || ''}:${current.user?.id || ''}` === requestWorkstation
    }
    try {
      let nextUser = null
      let response = null
      if (includeUser) {
        nextUser = await api('/auth/me', 'GET', null, { signal: controller.signal })
        if (
          controller.signal.aborted
          || requestId !== authorizationRequestRef.current
          || !credentialStillCurrent()
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
        || !credentialStillCurrent()
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
        || !credentialStillCurrent()
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

  const applyWorkstationSession = useCallback((session, { restoreContext = false } = {}) => {
    const nextUser = session?.user
    if (!session?.active || !nextUser || !session?.station) return false
    const next = { ...session, user: nextUser }
    const permissions = nextUser.uprawnienia || []
    workstationSessionRef.current = next
    userRef.current = nextUser
    setWorkstationSession(next)
    setUser(nextUser)
    setUprawnienia(permissions)
    setUprawnieniaReady(true)
    setLoading(false)
    setWorkstationIdleWarning(null)
    setWorkstationVersion((value) => value + 1)
    clearWorkstationLock()
    if (restoreContext) {
      restoreWorkstationReservationContext(session.station.id, nextUser.id, {
        state: reservationHistoryState(nextUser),
      })
    }
    return true
  }, [clearWorkstationLock])

  const enterWorkstationLock = useCallback(({ purge = true } = {}) => {
    if (workstationLockedRef.current) return
    const currentSession = workstationSessionRef.current
    if (currentSession?.station?.id && currentSession?.user?.id) {
      rememberWorkstationReservationContext(currentSession.station.id, currentSession.user.id)
    }
    authGenerationRef.current += 1
    rotateCredentialGeneration()
    cancelAuthorizationRefresh()
    workstationLockedRef.current = true
    workstationSessionRef.current = null
    userRef.current = null
    clearWorkstationCsrf()
    setWorkstationLocked(true)
    setWorkstationSession(null)
    setWorkstationIdleWarning(null)
    setUser(null)
    setLoading(false)
    setUprawnienia([])
    setUprawnieniaReady(false)
    if (purge) {
      purgeReservationPrivacy({ reason: 'workstation-locked' })
    }
  }, [cancelAuthorizationRefresh])

  const discoverWorkstation = useCallback(async ({ lock = true } = {}) => {
    const generation = authGenerationRef.current
    try {
      const gate = await api('/reservation-workstations/operators')
      if (generation !== authGenerationRef.current) return null
      workstationGateRef.current = gate
      setWorkstationGate(gate)
      if (lock) {
        workstationLockedRef.current = true
        setWorkstationLocked(true)
        setLoading(false)
      }
      return gate
    } catch (error) {
      if (generation !== authGenerationRef.current) return null
      if (error?.status === 401 && error?.code === 'WORKSTATION_NOT_REGISTERED') {
        workstationGateRef.current = null
        setWorkstationGate(null)
        clearWorkstationLock()
        setLoading(false)
        return null
      }
      if (lock) setLoading(false)
      throw error
    }
  }, [clearWorkstationLock])

  const lockWorkstation = useCallback(({ reason = 'manual' } = {}) => {
    const current = workstationSessionRef.current
    const request = current?.active
      ? api('/me/reservation-workstation/lock', 'POST', { reason }).catch(() => null)
      : Promise.resolve(null)
    enterWorkstationLock()
    void request.finally(() => discoverWorkstation({ lock: true }).catch(() => null))
    return request
  }, [discoverWorkstation, enterWorkstationLock])

  const unlockWorkstation = useCallback(async ({ userId, pin }) => {
    if (workstationCheckingRef.current) return null
    workstationCheckingRef.current = true
    setWorkstationChecking(true)
    try {
      const session = await api(
        '/reservation-workstations/unlock',
        'POST',
        { operator_id: Number(userId), pin },
        { headers: { 'X-Lokalo-Workstation-Intent': 'unlock' } },
      )
      authGenerationRef.current += 1
      rotateCredentialGeneration()
      cancelAuthorizationRefresh()
      setToken(null)
      purgeReservationPrivacy({ reason: 'login' })
      applyWorkstationSession(session, { restoreContext: true })
      return session
    } finally {
      workstationCheckingRef.current = false
      setWorkstationChecking(false)
    }
  }, [applyWorkstationSession, cancelAuthorizationRefresh])

  // Grant reautoryzacji jest celowo tylko wartością zwrotną. Nie trafia do stanu
  // kontekstu ani Web Storage i może zostać użyty od razu przez jedną operację.
  const reauthorizeWorkstation = useCallback(async ({
    pin,
    scope = 'reservation_override',
    signal,
  } = {}) => api(
    '/me/reservation-workstation/reauthorize',
    'POST',
    { pin, scope },
    {
      headers: { 'X-Lokalo-Workstation-Intent': 'reauthorize' },
      ...(signal ? { signal } : {}),
    },
  ), [])

  const forgetWorkstation = useCallback(async () => {
    const stationId = workstationGateRef.current?.station?.id
      || workstationSessionRef.current?.station?.id
    await api(
      '/reservation-workstations/forget-device',
      'POST',
      null,
      { headers: { 'X-Lokalo-Workstation-Intent': 'forget' } },
    )
    authGenerationRef.current += 1
    rotateCredentialGeneration()
    cancelAuthorizationRefresh()
    clearWorkstationCsrf()
    if (stationId) clearWorkstationReservationContexts(stationId)
    purgeReservationPrivacy({ reason: 'logout' })
    workstationGateRef.current = null
    workstationSessionRef.current = null
    userRef.current = null
    setWorkstationGate(null)
    setWorkstationSession(null)
    setUser(null)
    setUprawnienia([])
    setUprawnieniaReady(false)
    setLoading(false)
    clearWorkstationLock()
  }, [cancelAuthorizationRefresh, clearWorkstationLock])

  const logout = useCallback(() => {
    if (workstationSessionRef.current?.active) {
      void lockWorkstation()
      return
    }
    authGenerationRef.current += 1
    rotateCredentialGeneration()
    cancelAuthorizationRefresh()
    purgeReservationPrivacy({ reason: 'logout' })
    setToken(null)
    clearWorkstationCsrf()
    clearWorkstationLock()
    workstationSessionRef.current = null
    userRef.current = null
    setWorkstationSession(null)
    setUser(null)
    setUprawnienia([])
    setUprawnieniaReady(false)
    setLoading(false)
  }, [cancelAuthorizationRefresh, clearWorkstationLock, lockWorkstation])

  // Instalacja odbiornika cross-tab sprawia, że purge z innej karty czyści także
  // bieżący snapshot, nawet zanim przyszły ekran blokady stanowiska zostanie zamontowany.
  useEffect(() => {
    const unsubscribe = subscribeReservationPrivacyPurge((detail) => {
      if (detail?.reason === 'workstation-locked') {
        enterWorkstationLock({ purge: false })
        void discoverWorkstation({ lock: true }).catch(() => null)
        return
      }
      if (!detail?.external && detail?.reason === 'instance-change') {
        authGenerationRef.current += 1
        rotateCredentialGeneration()
        cancelAuthorizationRefresh()
        setToken(null)
        clearWorkstationCsrf()
        clearWorkstationLock()
        workstationGateRef.current = null
        workstationSessionRef.current = null
        userRef.current = null
        setWorkstationGate(null)
        setWorkstationSession(null)
        setUser(null)
        setUprawnienia([])
        setUprawnieniaReady(false)
        setLoading(false)
        return
      }
      if (!detail?.external) return

      if (detail.reason === 'authorization-change') {
        if (!getToken() && !workstationSessionRef.current?.active) return
        authGenerationRef.current += 1
        rotateCredentialGeneration()
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
        rotateCredentialGeneration()
        cancelAuthorizationRefresh()
        setToken(null)
        clearWorkstationCsrf()
        clearWorkstationLock()
        workstationSessionRef.current = null
        userRef.current = null
        setWorkstationSession(null)
        setUser(null)
        setUprawnienia([])
        setUprawnieniaReady(false)
        setLoading(false)
        return
      }
      if (detail.reason !== 'login') return

      const generation = ++authGenerationRef.current
      rotateCredentialGeneration()
      cancelAuthorizationRefresh()
      clearSessionToken()
      clearWorkstationLock()
      workstationSessionRef.current = null
      userRef.current = null
      setWorkstationSession(null)
      setUser(null)
      setUprawnienia([])
      setUprawnieniaReady(false)
      setLoading(true)
      const requestToken = getPersistentToken()
      if (!requestToken && !getWorkstationCsrf()) {
        setLoading(false)
        return
      }
      const endpoint = requestToken ? '/auth/me' : '/me/reservation-workstation'
      api(endpoint)
        .then((response) => {
          if (generation !== authGenerationRef.current) return
          if (requestToken) {
            if (getToken() !== requestToken) return
            userRef.current = response
            setUser(response)
            return
          }
          applyWorkstationSession(response, { restoreContext: true })
        })
        .catch(() => {})
        .finally(() => {
          if (generation === authGenerationRef.current) setLoading(false)
        })
    })
    return () => {
      authGenerationRef.current += 1
      unsubscribe()
    }
  }, [
    applyWorkstationSession,
    cancelAuthorizationRefresh,
    clearWorkstationLock,
    discoverWorkstation,
    enterWorkstationLock,
    refreshAuthorizationSnapshot,
  ])

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
      if (workstationSessionRef.current?.active || workstationGateRef.current) {
        enterWorkstationLock()
        void discoverWorkstation({ lock: true }).catch(() => null)
        return
      }
      authGenerationRef.current += 1
      rotateCredentialGeneration()
      cancelAuthorizationRefresh()
      purgeReservationPrivacy({ reason: 'unauthorized' })
      clearWorkstationLock()
      userRef.current = null
      setUser(null)
      setLoading(false)
    })
    setWorkstationLockedHandler(() => {
      enterWorkstationLock()
      void discoverWorkstation({ lock: true }).catch(() => null)
    })
    const clearSessionHandlers = () => {
      authGenerationRef.current += 1
      cancelAuthorizationRefresh()
      setUnauthorizedHandler(null)
      setWorkstationLockedHandler(null)
    }
    const t = getToken()
    const hasWorkstationCsrf = Boolean(getWorkstationCsrf())
    const workstationRequested = typeof window !== 'undefined'
      && new URLSearchParams(window.location.search).has('stanowisko')
    if (!t && !hasWorkstationCsrf && !workstationRequested) {
      setLoading(false)
      return clearSessionHandlers
    }
    const generation = authGenerationRef.current
    if (!t) {
      const initializeWorkstation = async () => {
        if (hasWorkstationCsrf) {
          try {
            const session = await api('/me/reservation-workstation')
            if (generation === authGenerationRef.current) {
              applyWorkstationSession(session, { restoreContext: true })
              return
            }
          } catch {
            // Sesja mogła wygasnąć; zarejestrowane urządzenie nadal może pokazać PIN gate.
          }
        }
        if (generation === authGenerationRef.current) {
          await discoverWorkstation({ lock: true }).catch(() => null)
        }
      }
      void initializeWorkstation().finally(() => {
        if (generation === authGenerationRef.current) setLoading(false)
      })
      return clearSessionHandlers
    }
    api('/auth/me')
      .then((nextUser) => {
        if (generation === authGenerationRef.current && getToken() === t) {
          userRef.current = nextUser
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
  }, [
    applyWorkstationSession,
    cancelAuthorizationRefresh,
    clearWorkstationLock,
    discoverWorkstation,
    enterWorkstationLock,
  ])

  const retryWorkstation = useCallback(async () => {
    if (workstationCheckingRef.current) return false
    workstationCheckingRef.current = true
    setWorkstationChecking(true)
    try {
      return Boolean(await discoverWorkstation({ lock: true }))
    } finally {
      workstationCheckingRef.current = false
      setWorkstationChecking(false)
    }
  }, [discoverWorkstation])

  const retryAuthorization = useCallback(
    () => refreshAuthorizationSnapshot({
      blocking: true,
      includeUser: !userRef.current,
    }),
    [refreshAuthorizationSnapshot],
  )

  // Polling nie przedłuża sesji. Tylko realna aktywność operatora odświeża
  // serwerowy idle timeout, a po jego upływie frontend natychmiast ukrywa PII.
  useEffect(() => {
    if (!workstationSession?.active || workstationLocked) return undefined
    const timeoutSeconds = Math.max(60, Number(workstationSession.idle_timeout_seconds) || 300)
    let lastActivityAt = Date.now()
    let lastTouchAt = 0
    let locked = false

    const touch = () => {
      if (locked) return
      const now = Date.now()
      lastActivityAt = now
      setWorkstationIdleWarning(null)
      if (now - lastTouchAt < 30000) return
      lastTouchAt = now
      void api('/me/reservation-workstation/touch', 'POST').catch(() => null)
    }
    const checkIdle = () => {
      if (locked) return
      const remaining = Math.ceil(timeoutSeconds - ((Date.now() - lastActivityAt) / 1000))
      if (remaining <= 0) {
        locked = true
        setWorkstationIdleWarning(null)
        void lockWorkstation({ reason: 'idle' })
        return
      }
      setWorkstationIdleWarning(remaining <= 30 ? remaining : null)
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') checkIdle()
    }

    window.addEventListener('pointerdown', touch, { passive: true })
    window.addEventListener('touchstart', touch, { passive: true })
    window.addEventListener('keydown', touch)
    document.addEventListener('visibilitychange', onVisibilityChange)
    const timer = window.setInterval(checkIdle, 1000)
    return () => {
      locked = true
      window.removeEventListener('pointerdown', touch)
      window.removeEventListener('touchstart', touch)
      window.removeEventListener('keydown', touch)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.clearInterval(timer)
      setWorkstationIdleWarning(null)
    }
  }, [lockWorkstation, workstationLocked, workstationSession])

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
    rotateCredentialGeneration()
    clearWorkstationCsrf()
    workstationSessionRef.current = null
    setWorkstationSession(null)
    establishAuthenticatedSession(res.access_token, remember)
    cancelAuthorizationRefresh()
    clearWorkstationLock()
    userRef.current = res.user
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
    rotateCredentialGeneration()
    clearWorkstationCsrf()
    workstationSessionRef.current = null
    setWorkstationSession(null)
    establishAuthenticatedSession(res.access_token)
    cancelAuthorizationRefresh()
    clearWorkstationLock()
    userRef.current = res.user
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
    workstationGate,
    workstationSession,
    workstationIdleWarning,
    workstationVersion,
    discoverWorkstation,
    unlockWorkstation,
    reauthorizeWorkstation,
    lockWorkstation,
    forgetWorkstation,
    retryWorkstation,
    authorizationRefreshing,
    authorizationError,
    retryAuthorization,
    can,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
