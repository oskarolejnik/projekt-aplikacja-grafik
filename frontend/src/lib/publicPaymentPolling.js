export const PUBLIC_PAYMENT_POLL_DELAYS_MS = Object.freeze([
  2_000,
  3_000,
  5_000,
  8_000,
  13_000,
  21_000,
  30_000,
])

export const publicPaymentNeedsPolling = (payment) => (
  payment?.status === 'oczekuje' || payment?.refund_status === 'oczekuje'
)

const visible = (visibilityTarget) => (
  !visibilityTarget || visibilityTarget.visibilityState !== 'hidden'
)

/**
 * Mały scheduler dla statusu płatności: pierwszy odczyt od razu, potem
 * ograniczony backoff. Ukrycie karty zatrzymuje timer i aktywne żądanie;
 * powrót wykonuje jeden świeży odczyt bez nadrabiania zaległych polli.
 */
export function createPublicPaymentPoller({
  poll,
  shouldContinue = () => true,
  onError = () => {},
  visibilityTarget = globalThis.document,
  delays = PUBLIC_PAYMENT_POLL_DELAYS_MS,
  setTimer = globalThis.setTimeout,
  clearTimer = globalThis.clearTimeout,
}) {
  if (typeof poll !== 'function') throw new TypeError('poll musi być funkcją')
  if (!Array.isArray(delays) || delays.length === 0) {
    throw new TypeError('delays musi zawierać co najmniej jeden odstęp')
  }

  let stopped = true
  let timer = null
  let controller = null
  let delayIndex = 0
  let running = false
  let refreshAfterRun = false

  const clearScheduled = () => {
    if (timer !== null) clearTimer(timer)
    timer = null
  }

  const schedule = () => {
    if (stopped || running || !shouldContinue() || !visible(visibilityTarget)) return
    const delay = delays[Math.min(delayIndex, delays.length - 1)]
    delayIndex += 1
    clearScheduled()
    timer = setTimer(() => {
      timer = null
      void execute()
    }, delay)
  }

  const execute = async () => {
    if (stopped || running || !shouldContinue() || !visible(visibilityTarget)) return
    running = true
    controller = new AbortController()
    try {
      await poll({ signal: controller.signal })
    } catch (error) {
      if (error?.name !== 'AbortError') onError(error)
    } finally {
      running = false
      controller = null
      if (refreshAfterRun && !stopped && visible(visibilityTarget) && shouldContinue()) {
        refreshAfterRun = false
        void execute()
        return
      }
      schedule()
    }
  }

  const onVisibilityChange = () => {
    clearScheduled()
    if (!visible(visibilityTarget)) {
      controller?.abort()
      return
    }
    delayIndex = 0
    if (running) {
      refreshAfterRun = true
      return
    }
    void execute()
  }

  return {
    start() {
      if (!stopped) return
      stopped = false
      visibilityTarget?.addEventListener?.('visibilitychange', onVisibilityChange)
      void execute()
    },
    stop() {
      if (stopped) return
      stopped = true
      refreshAfterRun = false
      clearScheduled()
      controller?.abort()
      visibilityTarget?.removeEventListener?.('visibilitychange', onVisibilityChange)
    },
    refresh() {
      if (stopped || !visible(visibilityTarget)) return
      delayIndex = 0
      clearScheduled()
      void execute()
    },
  }
}
