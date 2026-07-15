import { getApiBase } from './api'
import { normalizeReservationRoute } from './reservationRoute'

const PREFIX = 'lokalo:reservations:v1:'
const PRIVACY_EPOCH_KEY = 'lokalo:reservations:privacy-epoch:v1'
const HISTORY_ACTOR_KEY = 'lokaloReservationActor'
const HISTORY_EPOCH_KEY = 'lokaloReservationPrivacyEpoch'
let memoryPrivacyEpoch = null
let memoryPrivacyEpochAuthoritative = false

const newPrivacyEpoch = () => globalThis.crypto?.randomUUID?.()
  || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

const currentReservationPrivacyEpoch = () => {
  if (!memoryPrivacyEpochAuthoritative && typeof localStorage !== 'undefined') {
    try {
      const saved = localStorage.getItem(PRIVACY_EPOCH_KEY)
      if (saved) {
        memoryPrivacyEpoch = saved
        return saved
      }
      const created = newPrivacyEpoch()
      localStorage.setItem(PRIVACY_EPOCH_KEY, created)
      memoryPrivacyEpoch = created
      return created
    } catch {
      // Prywatny tryb może blokować storage; pamięć procesu nadal zamyka stare wpisy historii.
      memoryPrivacyEpochAuthoritative = true
    }
  }
  if (!memoryPrivacyEpoch) memoryPrivacyEpoch = newPrivacyEpoch()
  return memoryPrivacyEpoch
}

export const rotateReservationPrivacyEpoch = () => {
  const previous = currentReservationPrivacyEpoch()
  let next = newPrivacyEpoch()
  if (next === previous) {
    next = `${next}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  }
  memoryPrivacyEpoch = next
  if (!memoryPrivacyEpochAuthoritative && typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(PRIVACY_EPOCH_KEY, next)
    } catch {
      memoryPrivacyEpochAuthoritative = true
    }
  }
  return next
}

export const reservationActorKey = (user) => {
  const actor = user?.id ?? user?.login
  if (actor == null) return null
  const instance = getApiBase() || globalThis.location?.origin || 'local'
  return `${encodeURIComponent(instance)}:${encodeURIComponent(String(actor))}`
}

export const reservationHistoryState = (user) => {
  const actor = reservationActorKey(user)
  if (!actor) return {}
  return {
    [HISTORY_ACTOR_KEY]: actor,
    [HISTORY_EPOCH_KEY]: currentReservationPrivacyEpoch(),
  }
}

export const reservationHistoryBelongsTo = (user, state = globalThis.history?.state) => {
  const value = state && typeof state === 'object' ? state : {}
  const hasInternalReservationState = Object.keys(value)
    .some((key) => key.startsWith('lokaloReservation'))
  // Czysty deep link nie jest wpisem wewnętrznym i może zostać zweryfikowany przez API.
  if (!hasInternalReservationState) return true

  const expected = reservationHistoryState(user)
  // Stary wpis z samym aktorem jest celowo odrzucany: brak epoch po purge nie może
  // zostać potraktowany jak aktualny kontekst tego samego operatora.
  return Boolean(
    expected[HISTORY_ACTOR_KEY]
    && value[HISTORY_ACTOR_KEY] === expected[HISTORY_ACTOR_KEY]
    && typeof value[HISTORY_EPOCH_KEY] === 'string'
    && value[HISTORY_EPOCH_KEY] === expected[HISTORY_EPOCH_KEY],
  )
}

const storageKey = (user) => {
  const actor = reservationActorKey(user)
  return actor ? `${PREFIX}${actor}` : null
}

export function readReservationSession(user) {
  const key = storageKey(user)
  if (!key || typeof sessionStorage === 'undefined') return null
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || 'null')
    if (!saved || typeof saved !== 'object') return null
    if (saved.privacyEpoch !== currentReservationPrivacyEpoch()) {
      sessionStorage.removeItem(key)
      return null
    }
    const scroll = Object.fromEntries(
      Object.entries(saved.scroll || {})
        .filter(([view, value]) => ['today', 'calendar', 'database', 'host', 'availability', 'rooms'].includes(view)
          && Number.isFinite(value) && value >= 0),
    )
    return { route: normalizeReservationRoute(saved.route), scroll }
  } catch {
    sessionStorage.removeItem(key)
    return null
  }
}

export function writeReservationSession(user, { route, scroll = {} }) {
  const key = storageKey(user)
  if (!key || typeof sessionStorage === 'undefined') return
  const safeRoute = normalizeReservationRoute(route)
  const safeScroll = Object.fromEntries(
    Object.entries(scroll)
      .filter(([view, value]) => ['today', 'calendar', 'database', 'host', 'availability', 'rooms'].includes(view)
        && Number.isFinite(value) && value >= 0),
  )
  try {
    sessionStorage.setItem(key, JSON.stringify({
      privacyEpoch: currentReservationPrivacyEpoch(),
      route: safeRoute,
      scroll: safeScroll,
    }))
  } catch {
    // Brak miejsca lub prywatny tryb nie może blokować pracy operacyjnej.
  }
}

export function clearReservationSessions() {
  if (typeof sessionStorage === 'undefined') return
  try {
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith(PREFIX))
      .forEach((key) => sessionStorage.removeItem(key))
  } catch {
    // Czyszczenie jest best-effort; pamięć komponentów znika wraz z sesją React.
  }
}
