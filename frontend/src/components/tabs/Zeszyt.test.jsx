// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, toastMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  toastMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import Zeszyt from './Zeszyt'

const ZESZYT_Z_REDAKCJA = {
  stan_poczatkowy: null,
  stan_poczatkowy_data: null,
  dane_czesciowo_ukryte: true,
  dni: [{
    data: '2026-06-01',
    wiersze: [{
      zrodlo: 'SALA',
      gotowka: 500,
      terminal: 0,
      przelew: 0,
      impreza: 0,
      manualny: false,
    }],
    rozchod: [{ id: 1, kolumna: 'koszty', opis: 'Chemia', kwota: 80 }],
    przychod_gotowka: 500,
    rozchod_suma: 80,
    stan: null,
  }],
}

describe('Zeszyt read-only z ograniczonym dostępem', () => {
  beforeEach(() => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/szef/zeszyt?')) return Promise.resolve(ZESZYT_Z_REDAKCJA)
      return Promise.reject(new Error(`Nieoczekiwane żądanie: ${path}`))
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('pokazuje ukryte saldo bez mylącego zera i nie pobiera konfiguracji admina', async () => {
    render(<Zeszyt readOnly endpoint="/szef/zeszyt" />)

    await screen.findByText(/Pozycje wypłat i zależne od nich saldo są ukryte/)
    expect(screen.getAllByText('Ukryte')).toHaveLength(3)
    expect(screen.getByText('Chemia')).toBeInTheDocument()
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(expect.stringMatching(/^\/szef\/zeszyt\?/)))
    expect(apiMock).not.toHaveBeenCalledWith('/lokal/config')
  })
})
