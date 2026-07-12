// @vitest-environment jsdom
import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const { apiMock, authState, surfaceState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authState: {
    user: { rola: 'admin' },
    loading: false,
    workstationLocked: false,
    workstationChecking: false,
    retryWorkstation: vi.fn(),
    authorizationRefreshing: false,
    authorizationError: null,
    retryAuthorization: vi.fn(),
    logout: vi.fn(),
  },
  surfaceState: { dashboardError: false },
}))

vi.mock('./lib/api', () => ({
  api: apiMock,
  getApiBase: () => '',
}))
vi.mock('./lib/platforma', () => ({ jestNatywna: () => false }))
vi.mock('./context/AuthContext', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => authState,
}))
vi.mock('./context/BrandingContext', () => ({ BrandingProvider: ({ children }) => children }))
vi.mock('./context/DataContext', () => ({ DataProvider: ({ children }) => children }))
vi.mock('./components/ui/Toast', () => ({ ToastProvider: ({ children }) => children }))

vi.mock('./Dashboard', () => ({
  default: () => {
    if (surfaceState.dashboardError) throw new Error('dashboard chunk unavailable')
    return <div>Panel administratora</div>
  },
}))
vi.mock('./pages/SzefView', () => ({ default: () => <div>Panel managera</div> }))
vi.mock('./pages/SzefKuchniView', () => ({ default: () => <div>Panel szefa kuchni</div> }))
vi.mock('./pages/EmployeeArea', () => ({ default: () => <div>Panel pracownika</div> }))
vi.mock('./pages/ProduktPro', () => ({ default: () => <div>Strona produktu</div> }))

describe('App — powierzchnie ładowane na żądanie', () => {
  afterEach(cleanup)

  beforeEach(() => {
    apiMock.mockReset()
    apiMock.mockResolvedValue({ potrzebny: false })
    authState.user = { rola: 'admin' }
    authState.loading = false
    authState.workstationLocked = false
    authState.workstationChecking = false
    authState.retryWorkstation.mockReset()
    authState.authorizationRefreshing = false
    authState.authorizationError = null
    authState.retryAuthorization.mockReset()
    authState.logout.mockReset()
    surfaceState.dashboardError = false
  })

  it('pokazuje dostępny szkielet, zanim doładuje wybraną powierzchnię', () => {
    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent('Ładowanie aplikacji')
  })

  it('podczas sprawdzania sesji pokazuje stabilny szkielet zamiast pustego ekranu', () => {
    authState.loading = true
    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent('Sprawdzanie sesji')
  })

  it.each([
    ['admin', 'Panel administratora'],
    ['szef', 'Panel managera'],
    ['szef_kuchni', 'Panel szefa kuchni'],
    ['employee', 'Panel pracownika'],
  ])('zachowuje routing dla roli %s', async (rola, ekran) => {
    authState.user = { rola }
    render(<App />)

    expect(await screen.findByText(ekran)).toBeInTheDocument()
  })

  it('po blokadzie stanowiska nie montuje powierzchni roli ani danych operacyjnych', async () => {
    authState.workstationLocked = true
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Stanowisko jest zablokowane' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sprawdź ponownie' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wyloguj' })).toBeInTheDocument()
    expect(screen.queryByText('Panel administratora')).not.toBeInTheDocument()
  })

  it('podczas zewnętrznej zmiany roli fail-closed ukrywa panel aż do świeżego snapshotu', async () => {
    authState.authorizationRefreshing = true
    authState.authorizationError = 'Nie udało się odświeżyć uprawnień.'
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Nie udało się potwierdzić dostępu' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się odświeżyć uprawnień.')
    expect(screen.getByRole('button', { name: 'Spróbuj ponownie' })).toBeInTheDocument()
    expect(screen.queryByText('Panel administratora')).not.toBeInTheDocument()
  })

  it('ładuje publiczny produkt bez uruchamiania paneli ról', async () => {
    authState.user = null
    render(<App />)

    expect(await screen.findByText('Strona produktu')).toBeInTheDocument()
    expect(screen.queryByText('Panel administratora')).not.toBeInTheDocument()
    expect(screen.queryByText('Panel pracownika')).not.toBeInTheDocument()
  })

  it('pokazuje możliwość odświeżenia, gdy powierzchnia roli nie może się uruchomić', async () => {
    const consoleMock = vi.spyOn(console, 'error').mockImplementation(() => {})
    const preventError = (event) => event.preventDefault()
    window.addEventListener('error', preventError)
    surfaceState.dashboardError = true

    try {
      render(<App />)

      expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać widoku')
      expect(screen.getByRole('button', { name: 'Odśwież aplikację' })).toBeInTheDocument()
    } finally {
      window.removeEventListener('error', preventError)
      consoleMock.mockRestore()
    }
  })
})
