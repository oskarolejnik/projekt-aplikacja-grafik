// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, getTokenMock, setTokenMock, setUnauthorizedHandlerMock, routeClearMock, sessionsClearMock, authHandlers } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  getTokenMock: vi.fn(),
  setTokenMock: vi.fn(),
  setUnauthorizedHandlerMock: vi.fn(),
  routeClearMock: vi.fn(),
  sessionsClearMock: vi.fn(),
  authHandlers: { unauthorized: null },
}))

vi.mock('../lib/api', () => ({
  api: apiMock,
  getToken: getTokenMock,
  setToken: setTokenMock,
  setUnauthorizedHandler: setUnauthorizedHandlerMock,
}))
vi.mock('../lib/reservationRoute', () => ({ clearReservationRoute: routeClearMock }))
vi.mock('../lib/reservationSession', () => ({ clearReservationSessions: sessionsClearMock }))

import { AuthProvider, useAuth } from './AuthContext'

function Probe() {
  const { loading, uprawnieniaReady, uprawnienia, can, logout } = useAuth()
  return (
    <div>
      <span>{loading ? 'sesja-loading' : 'sesja-ready'}</span>
      <span>{uprawnieniaReady ? 'prawa-ready' : 'prawa-loading'}</span>
      <span>{can('grafik.podglad') ? 'ma-grafik' : 'brak-grafiku'}</span>
      <span>{can('wyplaty.podglad') ? 'ma-wyplaty' : 'brak-wyplat'}</span>
      <span>{uprawnienia.join(',')}</span>
      <button type="button" onClick={logout}>Wyloguj testowo</button>
    </div>
  )
}

describe('AuthContext permissions', () => {
  beforeEach(() => {
    getTokenMock.mockReturnValue('token')
    apiMock.mockReset()
    authHandlers.unauthorized = null
    setUnauthorizedHandlerMock.mockImplementation((handler) => { authHandlers.unauthorized = handler })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('ustawia gotowość i can() bez dodatkowego żądania, gdy UserOut zawiera uprawnienia', async () => {
    apiMock.mockResolvedValue({
      id: 7,
      login: 'manager',
      rola: 'szef',
      uprawnienia: ['grafik.podglad', 'raporty.podglad'],
      uprawnienia_override: {},
    })

    render(<AuthProvider><Probe /></AuthProvider>)

    await waitFor(() => expect(screen.getByText('prawa-ready')).toBeInTheDocument())
    expect(screen.getByText('sesja-ready')).toBeInTheDocument()
    expect(screen.getByText('ma-grafik')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/auth/me')
    expect(apiMock).not.toHaveBeenCalledWith('/me/uprawnienia')
  })

  it('utrzymuje zgodność ze starszą odpowiedzią i oznacza prawa jako gotowe po fallbacku', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') return Promise.resolve({ id: 7, login: 'manager', rola: 'szef' })
      if (path === '/me/uprawnienia') return Promise.resolve({ uprawnienia: ['grafik.podglad'] })
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })

    render(<AuthProvider><Probe /></AuthProvider>)

    await waitFor(() => expect(screen.getByText('prawa-ready')).toBeInTheDocument())
    expect(screen.getByText('ma-grafik')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/me/uprawnienia')
  })

  it('odświeża cofnięte uprawnienia po powrocie do otwartej aplikacji', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') {
        return Promise.resolve({
          id: 7,
          login: 'manager',
          rola: 'szef',
          uprawnienia: ['grafik.podglad', 'wyplaty.podglad'],
        })
      }
      if (path === '/me/uprawnienia') {
        return Promise.resolve({ uprawnienia: ['grafik.podglad'] })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })

    render(<AuthProvider><Probe /></AuthProvider>)

    await waitFor(() => expect(screen.getByText('ma-wyplaty')).toBeInTheDocument())
    window.dispatchEvent(new Event('focus'))

    await waitFor(() => expect(screen.getByText('brak-wyplat')).toBeInTheDocument())
    expect(screen.getByText('ma-grafik')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/me/uprawnienia')
  })

  it('czyści kontekst rezerwacji przy jawnym wylogowaniu', async () => {
    apiMock.mockResolvedValue({
      id: 7,
      login: 'manager',
      rola: 'szef',
      uprawnienia: ['rezerwacje.operacje'],
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByText('sesja-ready')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Wyloguj testowo' }))

    expect(sessionsClearMock).toHaveBeenCalledOnce()
    expect(routeClearMock).toHaveBeenCalledWith({ replace: true })
    expect(setTokenMock).toHaveBeenCalledWith(null)
  })

  it('czyści ten sam kontekst po odpowiedzi 401', async () => {
    apiMock.mockResolvedValue({
      id: 7,
      login: 'manager',
      rola: 'szef',
      uprawnienia: ['rezerwacje.operacje'],
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(authHandlers.unauthorized).toEqual(expect.any(Function)))

    act(() => authHandlers.unauthorized())

    expect(sessionsClearMock).toHaveBeenCalledOnce()
    expect(routeClearMock).toHaveBeenCalledWith({ replace: true })
  })
})
