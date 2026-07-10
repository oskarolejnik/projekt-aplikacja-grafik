// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, getTokenMock, setTokenMock, setUnauthorizedHandlerMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  getTokenMock: vi.fn(),
  setTokenMock: vi.fn(),
  setUnauthorizedHandlerMock: vi.fn(),
}))

vi.mock('../lib/api', () => ({
  api: apiMock,
  getToken: getTokenMock,
  setToken: setTokenMock,
  setUnauthorizedHandler: setUnauthorizedHandlerMock,
}))

import { AuthProvider, useAuth } from './AuthContext'

function Probe() {
  const { loading, uprawnieniaReady, uprawnienia, can } = useAuth()
  return (
    <div>
      <span>{loading ? 'sesja-loading' : 'sesja-ready'}</span>
      <span>{uprawnieniaReady ? 'prawa-ready' : 'prawa-loading'}</span>
      <span>{can('grafik.podglad') ? 'ma-grafik' : 'brak-grafiku'}</span>
      <span>{can('wyplaty.podglad') ? 'ma-wyplaty' : 'brak-wyplat'}</span>
      <span>{uprawnienia.join(',')}</span>
    </div>
  )
}

describe('AuthContext permissions', () => {
  beforeEach(() => {
    getTokenMock.mockReturnValue('token')
    apiMock.mockReset()
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
})
