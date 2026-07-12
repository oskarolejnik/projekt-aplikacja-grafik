// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getApiBase: () => 'https://lokal.example' }))

import {
  clearReservationSessions,
  readReservationSession,
  writeReservationSession,
} from './reservationSession'

beforeEach(() => {
  sessionStorage.clear()
})

describe('reservationSession', () => {
  it('izoluje bezpieczny kontekst między operatorami i nie utrwala obcych pól', () => {
    const ola = { id: 7, login: 'ola' }
    const jan = { id: 8, login: 'jan' }
    writeReservationSession(ola, {
      route: {
        view: 'database',
        from: '2026-07-01',
        to: '2026-07-31',
        status: 'potwierdzona',
        query: 'Kowalska',
        telefon: '500600700',
      },
      scroll: { database: 420, unknown: 900 },
    })

    const saved = readReservationSession(ola)
    expect(saved.route).toMatchObject({
      view: 'database',
      from: '2026-07-01',
      to: '2026-07-31',
      status: 'potwierdzona',
    })
    expect(saved.scroll).toEqual({ database: 420 })
    expect(readReservationSession(jan)).toBeNull()
    expect(JSON.stringify(sessionStorage)).not.toContain('Kowalska')
    expect(JSON.stringify(sessionStorage)).not.toContain('500600700')
  })

  it('czyści tylko namespacowaną pamięć workspace', () => {
    sessionStorage.setItem('inne-dane', 'zostają')
    writeReservationSession({ id: 7 }, { route: { view: 'today' } })

    clearReservationSessions()

    expect(sessionStorage.getItem('inne-dane')).toBe('zostają')
    expect(readReservationSession({ id: 7 })).toBeNull()
  })
})
