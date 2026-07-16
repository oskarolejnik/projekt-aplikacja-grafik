// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  PUBLIC_PAYMENT_POLL_DELAYS_MS,
  createPublicPaymentPoller,
  publicPaymentNeedsPolling,
} from './publicPaymentPolling'

class VisibilityTarget extends EventTarget {
  constructor() {
    super()
    this.visibilityState = 'visible'
  }

  set(value) {
    this.visibilityState = value
    this.dispatchEvent(new Event('visibilitychange'))
  }
}

const flush = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

afterEach(() => {
  vi.useRealTimers()
})

describe('createPublicPaymentPoller', () => {
  it('odpytuje od razu, potem z ograniczonym backoffem', async () => {
    vi.useFakeTimers()
    const poll = vi.fn().mockResolvedValue(undefined)
    const poller = createPublicPaymentPoller({ poll, visibilityTarget: new VisibilityTarget() })

    poller.start()
    await flush()
    expect(poll).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(PUBLIC_PAYMENT_POLL_DELAYS_MS[0] - 1)
    expect(poll).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(poll).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(PUBLIC_PAYMENT_POLL_DELAYS_MS[1])
    expect(poll).toHaveBeenCalledTimes(3)
    poller.stop()
  })

  it('pauzuje w ukrytej karcie i odświeża raz po powrocie', async () => {
    vi.useFakeTimers()
    const target = new VisibilityTarget()
    const poll = vi.fn().mockResolvedValue(undefined)
    const poller = createPublicPaymentPoller({ poll, visibilityTarget: target })

    poller.start()
    await flush()
    target.set('hidden')
    await vi.advanceTimersByTimeAsync(120_000)
    expect(poll).toHaveBeenCalledTimes(1)

    target.set('visible')
    await flush()
    expect(poll).toHaveBeenCalledTimes(2)
    poller.stop()
  })

  it('stop przerywa aktywne żądanie i nie planuje kolejnego', async () => {
    vi.useFakeTimers()
    let requestSignal
    const poll = vi.fn(({ signal }) => {
      requestSignal = signal
      return new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      })
    })
    const poller = createPublicPaymentPoller({ poll, visibilityTarget: new VisibilityTarget() })

    poller.start()
    await flush()
    poller.stop()
    await flush()

    expect(requestSignal.aborted).toBe(true)
    await vi.advanceTimersByTimeAsync(120_000)
    expect(poll).toHaveBeenCalledTimes(1)
  })

  it('po szybkim powrocie z ukrycia wykonuje świeży odczyt po zakończeniu abortu', async () => {
    vi.useFakeTimers()
    const target = new VisibilityTarget()
    const poll = vi.fn(({ signal }) => new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => {
        queueMicrotask(() => reject(new DOMException('Aborted', 'AbortError')))
      })
    }))
    const poller = createPublicPaymentPoller({ poll, visibilityTarget: target })

    poller.start()
    await flush()
    target.set('hidden')
    target.set('visible')
    await flush()
    await flush()

    expect(poll).toHaveBeenCalledTimes(2)
    poller.stop()
  })
})

describe('publicPaymentNeedsPolling', () => {
  it.each([
    [{ status: 'oczekuje', refund_status: 'brak' }, true],
    [{ status: 'oplacona', refund_status: 'oczekuje' }, true],
    [{ status: 'oplacona', refund_status: 'succeeded' }, false],
    [{ status: 'zwrocona', refund_status: 'succeeded' }, false],
  ])('rozpoznaje stan wymagający odświeżania %#', (payment, expected) => {
    expect(publicPaymentNeedsPolling(payment)).toBe(expected)
  })
})
