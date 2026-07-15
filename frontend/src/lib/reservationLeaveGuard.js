const activeGuards = new Map()
let pendingConfirmation = null
let nextGuardId = 0

export function registerReservationLeaveGuard(handler) {
  const id = ++nextGuardId
  activeGuards.set(id, handler)
  return () => {
    activeGuards.delete(id)
  }
}

export const hasReservationLeaveGuard = () => activeGuards.size > 0

export function confirmReservationLeave() {
  if (!activeGuards.size) return true
  if (pendingConfirmation) return pendingConfirmation
  const handlers = [...activeGuards.values()]
  pendingConfirmation = Promise.resolve()
    .then(async () => {
      for (const handler of handlers) {
        if (!(await handler())) return false
      }
      return true
    })
    .catch(() => false)
    .finally(() => { pendingConfirmation = null })
  return pendingConfirmation
}
