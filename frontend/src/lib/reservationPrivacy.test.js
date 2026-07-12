// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getApiBase: () => 'https://lokal.example' }))

import { navigateReservationRoute, readReservationRoute } from './reservationRoute'
import {
  readReservationSession,
  reservationHistoryState,
  rotateReservationPrivacyEpoch,
  writeReservationSession,
} from './reservationSession'
import {
  purgeReservationPrivacy,
  subscribeReservationPrivacyPurge,
} from './reservationPrivacy'

const user = { id: 7, login: 'ola' }

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState({}, '', '/')
})

describe('reservationPrivacy', () => {
  it('w trybie lock rotuje epoch i zachowuje wyłącznie bezpieczny kontekst dnia', () => {
    const before = reservationHistoryState(user).lokaloReservationPrivacyEpoch
    const listener = vi.fn()
    const unsubscribe = subscribeReservationPrivacyPurge(listener)
    writeReservationSession(user, {
      route: {
        view: 'calendar',
        date: '2026-08-17',
        status: 'potwierdzona',
        reservationId: 42,
        profileReservationId: 42,
      },
      scroll: { calendar: 240 },
    })
    navigateReservationRoute({
      view: 'calendar',
      date: '2026-08-17',
      status: 'potwierdzona',
      reservationId: 42,
      profileReservationId: 42,
    }, {
      replace: true,
      state: {
        ...reservationHistoryState(user),
        lokaloReservationGuestOverlay: true,
        lokaloReservationReturnTo: { view: 'calendar', date: '2026-08-17' },
      },
    })

    const detail = purgeReservationPrivacy({
      reason: 'workstation-locked',
      preserveSafeRoute: true,
    })

    const route = readReservationRoute()
    expect(detail).toMatchObject({
      reason: 'workstation-locked',
      preserveSafeRoute: true,
      external: false,
    })
    expect(detail.epoch).not.toBe(before)
    expect(route).toMatchObject({
      view: 'calendar',
      date: '2026-08-17',
      status: 'potwierdzona',
      reservationId: null,
      profileReservationId: null,
    })
    expect(window.location.hash).not.toContain('rezerwacja=')
    expect(window.location.hash).not.toContain('gosc=')
    expect(window.history.state).toEqual({})
    expect(readReservationSession(user)).toBeNull()
    expect(listener).toHaveBeenCalledWith(detail)
    expect(JSON.stringify(localStorage)).not.toContain('Kowalska')
    unsubscribe()
  })

  it('w trybie exit usuwa całą trasę rezerwacji', () => {
    navigateReservationRoute({ view: 'today', date: '2026-08-17', reservationId: 42 }, {
      replace: true,
      state: reservationHistoryState(user),
    })

    purgeReservationPrivacy({ reason: 'logout', broadcast: false })

    expect(window.location.hash).toBe('')
    expect(window.history.state).toEqual({})
  })

  it('sygnał z innej karty czyści lokalny snapshot bez ponownego broadcastu', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeReservationPrivacyPurge(listener)
    writeReservationSession(user, { route: { view: 'today', reservationId: 42 } })
    navigateReservationRoute({ view: 'today', date: '2026-08-17', reservationId: 42 }, {
      replace: true,
      state: reservationHistoryState(user),
    })
    const epoch = rotateReservationPrivacyEpoch()

    window.dispatchEvent(new StorageEvent('storage', {
      key: 'lokalo:reservations:privacy-purge:v1',
      newValue: JSON.stringify({
        epoch,
        reason: 'workstation-locked',
        preserveSafeRoute: true,
        nonce: 'inna-karta',
      }),
    }))

    expect(readReservationRoute()).toMatchObject({
      view: 'today',
      date: '2026-08-17',
      reservationId: null,
      profileReservationId: null,
    })
    expect(readReservationSession(user)).toBeNull()
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      epoch,
      external: true,
      reason: 'workstation-locked',
    }))
    unsubscribe()
  })
})
