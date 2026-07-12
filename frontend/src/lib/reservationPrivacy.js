import {
  clearReservationRoute,
  navigateReservationRoute,
  normalizeReservationRoute,
  readReservationRoute,
} from './reservationRoute'
import {
  clearReservationSessions,
  rotateReservationPrivacyEpoch,
} from './reservationSession'

const PURGE_EVENT = 'lokalo:reservation-privacy-purge'
const PURGE_SIGNAL_KEY = 'lokalo:reservations:privacy-purge:v1'
const SAFE_REASONS = new Set([
  'logout',
  'login',
  'unauthorized',
  'workstation-locked',
  'instance-change',
  'authorization-change',
  'manual',
])
let storageListenerInstalled = false

const safeReason = (reason) => SAFE_REASONS.has(reason) ? reason : 'manual'

const sanitizedRoute = (route) => normalizeReservationRoute({
  ...route,
  reservationId: null,
  profileReservationId: null,
})

const dispatchPurge = (detail) => {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(PURGE_EVENT, { detail }))
}

const applyPurge = ({
  epoch,
  reason = 'manual',
  preserveSafeRoute = false,
  external = false,
} = {}) => {
  const currentRoute = readReservationRoute()
  clearReservationSessions()

  if (preserveSafeRoute && currentRoute) {
    navigateReservationRoute(sanitizedRoute(currentRoute), {
      replace: true,
      clearReservationState: true,
    })
  } else {
    clearReservationRoute({ replace: true })
  }

  const detail = Object.freeze({
    epoch,
    reason: safeReason(reason),
    preserveSafeRoute: Boolean(preserveSafeRoute),
    external: Boolean(external),
  })
  dispatchPurge(detail)
  return detail
}

const installStorageListener = () => {
  if (storageListenerInstalled || typeof window === 'undefined') return
  storageListenerInstalled = true
  window.addEventListener('storage', (event) => {
    if (event.key !== PURGE_SIGNAL_KEY || !event.newValue) return
    try {
      const signal = JSON.parse(event.newValue)
      if (!signal || typeof signal.epoch !== 'string') return
      applyPurge({
        epoch: signal.epoch,
        reason: signal.reason,
        preserveSafeRoute: signal.preserveSafeRoute,
        external: true,
      })
    } catch {
      // Uszkodzony lub obcy sygnał storage nie może przerwać pracy aplikacji.
    }
  })
}

export function purgeReservationPrivacy({
  reason = 'manual',
  preserveSafeRoute = false,
  broadcast = true,
} = {}) {
  installStorageListener()
  const epoch = rotateReservationPrivacyEpoch()
  const detail = applyPurge({ epoch, reason, preserveSafeRoute })

  if (broadcast && typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(PURGE_SIGNAL_KEY, JSON.stringify({
        epoch,
        reason: detail.reason,
        preserveSafeRoute: detail.preserveSafeRoute,
        nonce: globalThis.crypto?.randomUUID?.()
          || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
      }))
    } catch {
      // Bieżąca karta została już wyczyszczona; brak storage nie może blokować purge.
    }
  }
  return detail
}

export function subscribeReservationPrivacyPurge(callback) {
  if (typeof window === 'undefined') return () => {}
  installStorageListener()
  const listener = (event) => callback(event.detail)
  window.addEventListener(PURGE_EVENT, listener)
  return () => window.removeEventListener(PURGE_EVENT, listener)
}
