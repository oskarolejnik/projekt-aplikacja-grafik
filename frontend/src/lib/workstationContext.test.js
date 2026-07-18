// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import {
  WORKSTATION_CONTEXT_STORAGE_KEY,
  clearWorkstationReservationContexts,
  rememberWorkstationReservationContext,
  restoreWorkstationReservationContext,
} from './workstationContext'

describe('workstationContext', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.replaceState({}, '', '/#/rezerwacje/dzisiaj?data=2026-07-18')
  })

  it('przywraca wyłącznie bezpieczny kontekst tego samego operatora i stanowiska', () => {
    rememberWorkstationReservationContext('front-desk', 7)
    window.history.replaceState({}, '', '/')

    expect(restoreWorkstationReservationContext('front-desk', 8)).toBeNull()
    expect(window.location.hash).toBe('')

    expect(restoreWorkstationReservationContext('front-desk', 7, {
      state: { lokaloReservationActor: 'operator-7' },
    })).toMatchObject({
      view: 'today',
      date: '2026-07-18',
    })
    expect(window.location.hash).toContain('#/rezerwacje/dzisiaj?data=2026-07-18')
    expect(window.history.state).toMatchObject({ lokaloReservationActor: 'operator-7' })
  })

  it('nigdy nie zapisuje identyfikatora rezerwacji, profilu gościa ani sali', () => {
    window.history.replaceState({}, '', '/#/rezerwacje/kalendarz?data=2026-07-18&rezerwacja=41&gosc=41')
    rememberWorkstationReservationContext('front-desk', 7)

    const raw = localStorage.getItem(WORKSTATION_CONTEXT_STORAGE_KEY)
    expect(raw).not.toContain('"reservationId":41')
    expect(raw).not.toContain('"profileReservationId":41')
    expect(raw).not.toContain('"roomId":')
  })

  it('usuwa wyłącznie konteksty wskazanego stanowiska', () => {
    rememberWorkstationReservationContext('front-desk', 7)
    rememberWorkstationReservationContext('garden-desk', 7)

    clearWorkstationReservationContexts('front-desk')

    expect(restoreWorkstationReservationContext('front-desk', 7)).toBeNull()
    expect(restoreWorkstationReservationContext('garden-desk', 7)).not.toBeNull()
  })
})
