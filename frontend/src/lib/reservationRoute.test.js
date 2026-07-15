// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildReservationHash,
  clearReservationRoute,
  isReservationHash,
  isValidDateIso,
  localDateIso,
  navigateReservationRoute,
  normalizeReservationRoute,
  readReservationRoute,
  subscribeReservationRoute,
} from './reservationRoute'

const BASE_URL = '/'

beforeEach(() => {
  window.history.replaceState({}, '', BASE_URL)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('reservationRoute', () => {
  it('rozpoznaje i odczytuje bezpośredni link do widoku rezerwacji', () => {
    const hash = '#/rezerwacje/kalendarz?data=2026-08-17&zakres=day&status=potwierdzona&rezerwacja=81&gosc=81'

    expect(isReservationHash(hash)).toBe(true)
    expect(isReservationHash('#/grafik')).toBe(false)
    expect(readReservationRoute(hash)).toMatchObject({
      view: 'calendar',
      date: '2026-08-17',
      mode: 'day',
      status: 'potwierdzona',
      reservationId: 81,
      profileReservationId: 81,
    })
    expect(readReservationRoute('#/grafik')).toBeNull()
  })

  it('buduje kanoniczny link dla każdego kontekstu roboczego', () => {
    expect(buildReservationHash({
      view: 'database',
      date: '2026-08-17',
      from: '2026-07-01',
      to: '2026-09-30',
      status: 'no_show',
      sort: 'nazwisko_asc',
      offset: 50,
      reservationId: 123,
      profileReservationId: 123,
    })).toBe(
      '#/rezerwacje/baza?od=2026-07-01&do=2026-09-30&status=no_show&sort=nazwisko_asc&offset=50&rezerwacja=123&gosc=123',
    )

    expect(buildReservationHash({
      view: 'today',
      date: '2026-08-17',
    })).toBe('#/rezerwacje/dzisiaj?data=2026-08-17')

    expect(buildReservationHash({
      view: 'rooms',
      roomId: 7,
    })).toBe('#/rezerwacje/sale?sala=7')

    expect(buildReservationHash({
      view: 'availability',
      date: '2026-08-17',
    })).toBe('#/rezerwacje/dostepnosc')
  })

  it('normalizuje niepoprawne wartości i zakres dat', () => {
    expect(isValidDateIso('2026-02-29')).toBe(false)
    expect(isValidDateIso('2028-02-29')).toBe(true)

    expect(normalizeReservationRoute({
      view: 'sekret',
      date: '2026-02-29',
      mode: 'month',
      status: 'nieznany',
      from: '2026-09-30',
      to: '2026-07-01',
      sort: 'losowo',
      offset: -12,
      reservationId: '-4',
      profileReservationId: 'nie-id',
    }, '2026-08-17')).toEqual({
      view: 'today',
      date: '2026-08-17',
      mode: 'week',
      status: '',
      from: '2026-07-01',
      to: '2026-09-30',
      sort: 'data_desc',
      offset: 0,
      reservationId: null,
      profileReservationId: null,
      roomId: null,
    })
  })

  it('profil gościa zawsze wskazuje tę samą rezerwację co zaznaczenie', () => {
    const normalized = normalizeReservationRoute({
      view: 'today',
      date: '2026-08-17',
      reservationId: 41,
      profileReservationId: 42,
    })

    expect(normalized.reservationId).toBe(42)
    expect(normalized.profileReservationId).toBe(42)
    expect(buildReservationHash(normalized)).toContain('rezerwacja=42&gosc=42')
  })

  it('wyznacza Dzisiaj zawsze w strefie Europe/Warsaw', () => {
    expect(localDateIso(new Date('2026-07-12T22:30:00.000Z'))).toBe('2026-07-13')
    expect(localDateIso(new Date('2026-01-01T23:30:00.000Z'))).toBe('2026-01-02')
  })

  it('nigdy nie zapisuje danych osobowych ani frazy wyszukiwania w URL', () => {
    const hash = buildReservationHash({
      view: 'database',
      from: '2026-07-01',
      to: '2026-09-30',
      query: 'Kowalska',
      q: 'Kowalska',
      nazwisko: 'Kowalska',
      phone: '+48 500 600 700',
      telefon: '+48 500 600 700',
      klucz: '+48 500 600 700',
    })

    expect(hash).not.toContain('Kowalska')
    expect(hash).not.toContain('500')
    expect(hash).not.toMatch(/(?:query|q|nazwisko|phone|telefon|klucz)=/)
  })

  it('powiadamia subskrybenta po nawigacji i zdarzeniu Back bez ręcznego parsowania URL', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeReservationRoute(listener)

    navigateReservationRoute({ view: 'calendar', date: '2026-08-17' })
    expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({
      view: 'calendar',
      date: '2026-08-17',
    }), expect.objectContaining({ type: 'lokalo:reservation-route' }))

    window.history.replaceState({}, '', '#/rezerwacje/dzisiaj?data=2026-08-16')
    window.dispatchEvent(new PopStateEvent('popstate'))
    expect(listener).toHaveBeenLastCalledWith(expect.objectContaining({
      view: 'today',
      date: '2026-08-16',
    }), expect.objectContaining({ type: 'popstate' }))

    unsubscribe()
    window.dispatchEvent(new PopStateEvent('popstate'))
    expect(listener).toHaveBeenCalledTimes(2)
  })

  it('przy czyszczeniu usuwa znaczniki operatora i panelu z bieżącego wpisu historii', () => {
    window.history.replaceState({
      lokaloReservationActor: 'lokal:7',
      lokaloReservationOverlay: true,
      lokaloReservationGuestOverlay: true,
      lokaloReservationReturnTo: { view: 'today', date: '2026-08-17' },
      lokaloReservationPrivacyEpoch: 'epoch-1',
      lokaloDashboardTab: 'rezerwacje',
    }, '', '/#/rezerwacje/dzisiaj?data=2026-08-17&rezerwacja=42&gosc=42')

    clearReservationRoute({ replace: true })

    expect(window.location.hash).toBe('')
    expect(window.history.state).toEqual({ lokaloDashboardTab: 'rezerwacje' })
  })
})
