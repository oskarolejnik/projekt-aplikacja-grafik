// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const {
  sprawdzInstancjeMock,
  setApiBaseMock,
  setTokenMock,
  purgeMock,
} = vi.hoisted(() => ({
  sprawdzInstancjeMock: vi.fn(),
  setApiBaseMock: vi.fn(),
  setTokenMock: vi.fn(),
  purgeMock: vi.fn(),
}))

vi.mock('../lib/api', () => ({
  sprawdzInstancje: sprawdzInstancjeMock,
  setApiBase: setApiBaseMock,
  setToken: setTokenMock,
}))
vi.mock('../lib/reservationPrivacy', () => ({ purgeReservationPrivacy: purgeMock }))
vi.mock('../components/Logo', () => ({ Logo: () => <span>Lokalo</span> }))
vi.mock('../components/ui/Spinner', () => ({ Spinner: () => <span>Ładowanie</span> }))

import WyborInstancji from './WyborInstancji'

beforeEach(() => {
  sprawdzInstancjeMock.mockResolvedValue(true)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('WyborInstancji', () => {
  it('przed zmianą lokalu czyści kontekst operatora przez wspólny purge', async () => {
    const onGotowe = vi.fn()
    render(<WyborInstancji onGotowe={onGotowe} />)
    fireEvent.change(screen.getByPlaceholderText('https://mojlokal.lokalo.pl'), {
      target: { value: 'lokal.example' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Połącz' }))

    await waitFor(() => expect(onGotowe).toHaveBeenCalledOnce())
    expect(sprawdzInstancjeMock).toHaveBeenCalledWith('https://lokal.example')
    expect(purgeMock).toHaveBeenCalledWith({ reason: 'instance-change' })
    expect(setTokenMock).toHaveBeenCalledWith(null)
    expect(setApiBaseMock).toHaveBeenCalledWith('https://lokal.example')
  })
})
