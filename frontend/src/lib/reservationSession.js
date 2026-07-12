import { getApiBase } from './api'
import { normalizeReservationRoute } from './reservationRoute'

const PREFIX = 'lokalo:reservations:v1:'

export const reservationActorKey = (user) => {
  const actor = user?.id ?? user?.login
  if (actor == null) return null
  const instance = getApiBase() || globalThis.location?.origin || 'local'
  return `${encodeURIComponent(instance)}:${encodeURIComponent(String(actor))}`
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
    const scroll = Object.fromEntries(
      Object.entries(saved.scroll || {})
        .filter(([view, value]) => ['today', 'calendar', 'database', 'host'].includes(view)
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
      .filter(([view, value]) => ['today', 'calendar', 'database', 'host'].includes(view)
        && Number.isFinite(value) && value >= 0),
  )
  try {
    sessionStorage.setItem(key, JSON.stringify({ route: safeRoute, scroll: safeScroll }))
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
