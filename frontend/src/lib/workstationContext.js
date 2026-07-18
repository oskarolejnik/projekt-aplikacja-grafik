import {
  navigateReservationRoute,
  normalizeReservationRoute,
  readReservationRoute,
} from './reservationRoute'

const STORAGE_KEY = 'lokalo:reservation-workstation-context:v1'
const SAFE_VIEWS = new Set(['today', 'calendar', 'database', 'host'])
const MAX_CONTEXTS = 24

const contextKey = (stationId, userId) => `${String(stationId || '')}:${String(userId || '')}`

function readStore() {
  if (typeof localStorage === 'undefined') return {}
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  } catch {
    return {}
  }
}

function writeStore(value) {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Brak storage nie może blokować bezpiecznej blokady stanowiska.
  }
}

function safeRoute(value) {
  if (!value) return null
  const normalized = normalizeReservationRoute({
    ...value,
    reservationId: null,
    profileReservationId: null,
    roomId: null,
  })
  if (!SAFE_VIEWS.has(normalized.view)) return null
  const {
    reservationId: _reservationId,
    profileReservationId: _profileReservationId,
    roomId: _roomId,
    ...route
  } = normalized
  return route
}

export function rememberWorkstationReservationContext(stationId, userId) {
  if (!stationId || !userId) return null
  const route = safeRoute(readReservationRoute())
  if (!route) return null

  const store = readStore()
  store[contextKey(stationId, userId)] = { route, savedAt: Date.now() }
  const entries = Object.entries(store)
    .sort(([, first], [, second]) => Number(second?.savedAt || 0) - Number(first?.savedAt || 0))
    .slice(0, MAX_CONTEXTS)
  writeStore(Object.fromEntries(entries))
  return route
}

export function restoreWorkstationReservationContext(stationId, userId, { state = {} } = {}) {
  if (!stationId || !userId) return null
  const route = safeRoute(readStore()[contextKey(stationId, userId)]?.route)
  if (!route) return null
  navigateReservationRoute(route, {
    replace: true,
    clearReservationState: true,
    state,
  })
  return route
}

export function clearWorkstationReservationContexts(stationId = null) {
  if (typeof localStorage === 'undefined') return
  if (!stationId) {
    localStorage.removeItem(STORAGE_KEY)
    return
  }
  const prefix = `${String(stationId)}:`
  const next = Object.fromEntries(
    Object.entries(readStore()).filter(([key]) => !key.startsWith(prefix)),
  )
  writeStore(next)
}

export { STORAGE_KEY as WORKSTATION_CONTEXT_STORAGE_KEY }
