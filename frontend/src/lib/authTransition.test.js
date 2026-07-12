import { beforeEach, describe, expect, it, vi } from 'vitest'

const { purgeMock, setTokenMock } = vi.hoisted(() => ({
  purgeMock: vi.fn(),
  setTokenMock: vi.fn(),
}))

vi.mock('./api', () => ({ setToken: setTokenMock }))
vi.mock('./reservationPrivacy', () => ({ purgeReservationPrivacy: purgeMock }))

import { establishAuthenticatedSession } from './authTransition'

describe('establishAuthenticatedSession', () => {
  beforeEach(() => vi.clearAllMocks())

  it('czyści prywatny kontekst przed zapisaniem tokenu nowego operatora', () => {
    establishAuthenticatedSession('nowy-token')

    expect(purgeMock).toHaveBeenCalledWith({ reason: 'login' })
    expect(setTokenMock).toHaveBeenCalledWith('nowy-token')
    expect(purgeMock.mock.invocationCallOrder[0]).toBeLessThan(setTokenMock.mock.invocationCallOrder[0])
  })

  it('przekazuje wybór trwałości sesji', () => {
    establishAuthenticatedSession('token-sesyjny', false)

    expect(setTokenMock).toHaveBeenCalledWith('token-sesyjny', false)
  })
})
