let activeGuard = null
let pendingConfirmation = null

export function registerReservationLeaveGuard(handler) {
  activeGuard = handler
  return () => {
    if (activeGuard === handler) activeGuard = null
  }
}

export const hasReservationLeaveGuard = () => typeof activeGuard === 'function'

export function confirmReservationLeave() {
  if (!activeGuard) return true
  if (pendingConfirmation) return pendingConfirmation
  const handler = activeGuard
  pendingConfirmation = Promise.resolve()
    .then(() => handler())
    .then(Boolean)
    .catch(() => false)
    .finally(() => { pendingConfirmation = null })
  return pendingConfirmation
}
