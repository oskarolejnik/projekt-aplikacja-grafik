// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, toastMock } = vi.hoisted(() => ({ apiMock: vi.fn(), toastMock: vi.fn() }))

vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../components/ui/Card', () => ({
  Card: ({ children, className = '', ...props }) => <div className={className} {...props}>{children}</div>,
}))
vi.mock('../components/ui/Spinner', () => ({ Spinner: () => <span>Ładowanie</span> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import EmployeeHours from './EmployeeHours'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('EmployeeHours', () => {
  it('pokazuje godziny i wypłatę przed obsługą zaliczek', async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/me/godziny')) {
        return Promise.resolve({ suma_godzin: 8, do_wyplaty: 240, stanowiska: [], dni: [], aktywna_zmiana: null })
      }
      if (path.startsWith('/me/portfel')) {
        return Promise.resolve({ zarobek: 240, dostepna_zaliczka: 120, limit_procent: 50, zaliczki: [] })
      }
      if (path.startsWith('/me/napiwki')) return Promise.resolve({ suma: 0, dni: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<EmployeeHours />)

    const podsumowanie = await screen.findByText('Łącznie w miesiącu')
    const zaliczka = await screen.findByText(/Dostępna zaliczka:/)
    expect(podsumowanie.compareDocumentPosition(zaliczka) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('08:00')).toBeInTheDocument()
    expect(screen.getAllByText('240,00 zł').length).toBeGreaterThan(0)
  })

  const mockRcp = (rcp) => {
    apiMock.mockImplementation((path, method, body) => {
      if (path === '/me/rcp') return Promise.resolve(rcp)
      if (path === '/me/rcp/odbij') {
        return Promise.resolve({ kierunek: 'wejscie', data: '2026-07-20', czas: '2026-07-20T10:00:00' })
      }
      if (path.startsWith('/me/godziny')) {
        return Promise.resolve({ suma_godzin: 0, do_wyplaty: 0, stanowiska: [], dni: [], aktywna_zmiana: null })
      }
      if (path.startsWith('/me/portfel')) {
        return Promise.resolve({ zarobek: 0, dostepna_zaliczka: 0, limit_procent: 50, zaliczki: [] })
      }
      if (path.startsWith('/me/napiwki')) return Promise.resolve({ suma: 0, dni: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
  }

  it('odbija wejście telefonem: pobiera pozycję i wysyła ją na /me/rcp/odbij', async () => {
    mockRcp({ aktywne: true, promien_m: 150, zmiana: null })
    const getCurrentPosition = vi.fn((ok) => ok({ coords: { latitude: 50, longitude: 19, accuracy: 12 } }))
    vi.stubGlobal('navigator', { ...window.navigator, geolocation: { getCurrentPosition } })

    render(<EmployeeHours />)
    fireEvent.click(await screen.findByRole('button', { name: 'Rozpocznij zmianę' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/me/rcp/odbij', 'POST', { lat: 50, lng: 19, dokladnosc_m: 12 }))
    expect(toastMock).toHaveBeenCalledWith(expect.stringContaining('Zmiana rozpoczęta o 10:00'), 'success')
    vi.unstubAllGlobals()
  })

  it('przy otwartej zmianie GEO pokazuje „Zakończ zmianę" z godziną startu', async () => {
    mockRcp({ aktywne: true, promien_m: 150, zmiana: { data: '2026-07-20', wejscie: '2026-07-20T09:30:00' } })
    render(<EmployeeHours />)
    expect(await screen.findByRole('button', { name: 'Zakończ zmianę' })).toBeInTheDocument()
    expect(screen.getByText(/Rozpoczęta o 09:30/)).toBeInTheDocument()
  })

  it('bez włączonego RCP mobilnego nie pokazuje karty odbicia', async () => {
    mockRcp({ aktywne: false, zmiana: null })
    render(<EmployeeHours />)
    await screen.findByText('Łącznie w miesiącu')
    expect(screen.queryByRole('button', { name: 'Rozpocznij zmianę' })).not.toBeInTheDocument()
  })
})
