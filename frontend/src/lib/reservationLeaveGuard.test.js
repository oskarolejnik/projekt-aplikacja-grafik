import { describe, expect, it, vi } from 'vitest'
import {
  confirmReservationLeave,
  hasReservationLeaveGuard,
  registerReservationLeaveGuard,
} from './reservationLeaveGuard'

describe('reservationLeaveGuard', () => {
  it('nie gubi wcześniejszego szkicu, gdy dwa widoki konfiguracji są brudne', async () => {
    const first = vi.fn().mockResolvedValue(true)
    const second = vi.fn().mockResolvedValue(true)
    const unregisterFirst = registerReservationLeaveGuard(first)
    const unregisterSecond = registerReservationLeaveGuard(second)

    expect(hasReservationLeaveGuard()).toBe(true)
    await expect(confirmReservationLeave()).resolves.toBe(true)
    expect(first).toHaveBeenCalledOnce()
    expect(second).toHaveBeenCalledOnce()

    unregisterSecond()
    unregisterFirst()
    expect(hasReservationLeaveGuard()).toBe(false)
  })

  it('zatrzymuje wyjście po pierwszej odmowie', async () => {
    const first = vi.fn().mockResolvedValue(false)
    const second = vi.fn().mockResolvedValue(true)
    const unregisterFirst = registerReservationLeaveGuard(first)
    const unregisterSecond = registerReservationLeaveGuard(second)

    await expect(confirmReservationLeave()).resolves.toBe(false)
    expect(second).not.toHaveBeenCalled()

    unregisterSecond()
    unregisterFirst()
  })
})
