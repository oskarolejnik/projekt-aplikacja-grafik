// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const {
  apiMock,
  getTokenMock,
  getPersistentTokenMock,
  clearSessionTokenMock,
  setTokenMock,
  setUnauthorizedHandlerMock,
  setWorkstationLockedHandlerMock,
  purgeMock,
  subscribePurgeMock,
  privacyState,
  authHandlers,
} = vi.hoisted(() => {
  const privacyState = { callback: null }
  return {
    apiMock: vi.fn(),
    getTokenMock: vi.fn(),
    getPersistentTokenMock: vi.fn(),
    clearSessionTokenMock: vi.fn(),
    setTokenMock: vi.fn(),
    setUnauthorizedHandlerMock: vi.fn(),
    setWorkstationLockedHandlerMock: vi.fn(),
    purgeMock: vi.fn(),
    privacyState,
    subscribePurgeMock: vi.fn((callback) => {
      privacyState.callback = callback
      return vi.fn()
    }),
    authHandlers: { unauthorized: null, workstationLocked: null },
  }
})

vi.mock('../lib/api', () => ({
  api: apiMock,
  getToken: getTokenMock,
  getPersistentToken: getPersistentTokenMock,
  clearSessionToken: clearSessionTokenMock,
  setToken: setTokenMock,
  setUnauthorizedHandler: setUnauthorizedHandlerMock,
  setWorkstationLockedHandler: setWorkstationLockedHandlerMock,
}))
vi.mock('../lib/reservationPrivacy', () => ({
  purgeReservationPrivacy: purgeMock,
  subscribeReservationPrivacyPurge: subscribePurgeMock,
}))

import { AuthProvider, useAuth } from './AuthContext'

function Probe() {
  const {
    loading,
    uprawnieniaReady,
    uprawnienia,
    user,
    workstationLocked,
    can,
    login,
    register,
    logout,
    retryWorkstation,
    authorizationRefreshing,
    authorizationError,
  } = useAuth()
  return (
    <div>
      <span>{loading ? 'sesja-loading' : 'sesja-ready'}</span>
      <span>{uprawnieniaReady ? 'prawa-ready' : 'prawa-loading'}</span>
      <span>{can('grafik.podglad') ? 'ma-grafik' : 'brak-grafiku'}</span>
      <span>{can('wyplaty.podglad') ? 'ma-wyplaty' : 'brak-wyplat'}</span>
      <span>{uprawnienia.join(',')}</span>
      <span>operator-{user?.login || 'brak'}</span>
      <span>rola-{user?.rola || 'brak'}</span>
      <span>{user?.rola === 'admin' ? 'tryb-admin' : 'tryb-nie-admin'}</span>
      <span>{workstationLocked ? 'stanowisko-locked' : 'stanowisko-open'}</span>
      <span>{authorizationRefreshing ? 'autoryzacja-refreshing' : 'autoryzacja-ready'}</span>
      <span>{authorizationError || 'autoryzacja-ok'}</span>
      <button type="button" onClick={() => login('nowy-manager', 'haslo')}>Zaloguj ponownie</button>
      <button type="button" onClick={() => register({ login: 'nowy-manager', haslo: 'haslo' })}>Zarejestruj ponownie</button>
      <button type="button" onClick={logout}>Wyloguj testowo</button>
      <button type="button" onClick={retryWorkstation}>Sprawdź stanowisko</button>
    </div>
  )
}

describe('AuthContext permissions', () => {
  beforeEach(() => {
    getTokenMock.mockReturnValue('token')
    getPersistentTokenMock.mockReturnValue('token')
    apiMock.mockReset()
    authHandlers.unauthorized = null
    authHandlers.workstationLocked = null
    privacyState.callback = null
    setUnauthorizedHandlerMock.mockImplementation((handler) => { authHandlers.unauthorized = handler })
    setWorkstationLockedHandlerMock.mockImplementation((handler) => { authHandlers.workstationLocked = handler })
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
    expect(apiMock.mock.calls.some(([path]) => path === '/me/uprawnienia')).toBe(false)
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
    expect(apiMock).toHaveBeenCalledWith(
      '/me/uprawnienia', 'GET', null, expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
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
    expect(apiMock).toHaveBeenCalledWith(
      '/me/uprawnienia', 'GET', null, expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('atomowo odbiera tryb admina i purge PII po zmianie roli na serwerze', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') {
        return Promise.resolve({
          id: 7,
          login: 'admin',
          rola: 'admin',
          uprawnienia: ['rezerwacje.dane_wrazliwe', 'rezerwacje.notatki_wewnetrzne'],
        })
      }
      if (path === '/me/uprawnienia') {
        return Promise.resolve({ rola: 'szef', uprawnienia: ['grafik.podglad'] })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('tryb-admin')).toBeInTheDocument()

    window.dispatchEvent(new Event('focus'))

    expect(await screen.findByText('rola-szef')).toBeInTheDocument()
    expect(screen.getByText('tryb-nie-admin')).toBeInTheDocument()
    expect(screen.getByText('ma-grafik')).toBeInTheDocument()
    expect(purgeMock).toHaveBeenCalledWith({
      reason: 'authorization-change',
      preserveSafeRoute: true,
    })
  })

  it('synchronizuje zmianę roli rozgłoszoną z innej karty', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') {
        return Promise.resolve({ id: 7, login: 'admin', rola: 'admin', uprawnienia: [] })
      }
      if (path === '/me/uprawnienia') {
        return Promise.resolve({ rola: 'szef', uprawnienia: ['grafik.podglad'] })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('tryb-admin')).toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'authorization-change', external: true }))

    expect(await screen.findByText('rola-szef')).toBeInTheDocument()
    expect(screen.getByText('ma-grafik')).toBeInTheDocument()
  })

  it('pozostaje fail-closed po błędzie odświeżenia autoryzacji z innej karty', async () => {
    let rejectAuthorization
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') {
        return Promise.resolve({ id: 7, login: 'admin', rola: 'admin', uprawnienia: [] })
      }
      if (path === '/me/uprawnienia') {
        return new Promise((_, reject) => { rejectAuthorization = reject })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('tryb-admin')).toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'authorization-change', external: true }))

    expect(await screen.findByText('autoryzacja-refreshing')).toBeInTheDocument()
    await act(async () => {
      rejectAuthorization(new Error('Nie udało się potwierdzić dostępu.'))
    })

    expect(await screen.findByText('Nie udało się potwierdzić dostępu.')).toBeInTheDocument()
    expect(screen.getByText('autoryzacja-refreshing')).toBeInTheDocument()
    expect(screen.getByText('prawa-loading')).toBeInTheDocument()
  })

  it('ignoruje starszy snapshot autoryzacji po nowszym odświeżeniu z innej karty', async () => {
    const requests = []
    apiMock.mockImplementation((path, _method, _body, options) => {
      if (path === '/auth/me') {
        return Promise.resolve({ id: 7, login: 'admin', rola: 'admin', uprawnienia: [] })
      }
      if (path === '/me/uprawnienia') {
        return new Promise((resolve) => requests.push({ resolve, signal: options?.signal }))
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('tryb-admin')).toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'authorization-change', external: true }))
    await waitFor(() => expect(requests).toHaveLength(1))
    act(() => privacyState.callback?.({ reason: 'authorization-change', external: true }))
    await waitFor(() => expect(requests).toHaveLength(2))
    expect(requests[0].signal.aborted).toBe(true)

    await act(async () => {
      requests[1].resolve({ rola: 'szef', uprawnienia: ['grafik.podglad'] })
    })
    expect(await screen.findByText('rola-szef')).toBeInTheDocument()
    expect(screen.getByText('autoryzacja-ready')).toBeInTheDocument()

    await act(async () => {
      requests[0].resolve({ rola: 'admin', uprawnienia: ['wyplaty.podglad'] })
    })
    expect(screen.getByText('rola-szef')).toBeInTheDocument()
    expect(screen.getByText('brak-wyplat')).toBeInTheDocument()
  })

  it('unieważnia spóźnione /auth/me po zmianie autoryzacji z innej karty', async () => {
    let resolveStaleUser
    let authMeCalls = 0
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') {
        authMeCalls += 1
        if (authMeCalls === 1) {
          return new Promise((resolve) => { resolveStaleUser = resolve })
        }
        return Promise.resolve({
          id: 7,
          login: 'manager',
          rola: 'szef',
          uprawnienia: ['grafik.podglad'],
        })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(authMeCalls).toBe(1))

    act(() => privacyState.callback?.({ reason: 'authorization-change', external: true }))

    expect(await screen.findByText('rola-szef')).toBeInTheDocument()
    expect(screen.getByText('ma-grafik')).toBeInTheDocument()
    expect(screen.getByText('autoryzacja-ready')).toBeInTheDocument()

    await act(async () => {
      resolveStaleUser({
        id: 7,
        login: 'admin',
        rola: 'admin',
        uprawnienia: ['wyplaty.podglad'],
      })
    })
    expect(screen.getByText('rola-szef')).toBeInTheDocument()
    expect(screen.getByText('tryb-nie-admin')).toBeInTheDocument()
    expect(screen.getByText('brak-wyplat')).toBeInTheDocument()
  })

  it('ignoruje zmianę autoryzacji z innej karty, gdy ta karta nie ma sesji', async () => {
    getTokenMock.mockReturnValue(null)
    getPersistentTokenMock.mockReturnValue(null)
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('sesja-ready')).toBeInTheDocument()
    await waitFor(() => expect(privacyState.callback).toEqual(expect.any(Function)))

    act(() => privacyState.callback?.({ reason: 'authorization-change', external: true }))

    expect(screen.getByText('autoryzacja-ready')).toBeInTheDocument()
    expect(screen.getByText('autoryzacja-ok')).toBeInTheDocument()
    expect(screen.getByText('operator-brak')).toBeInTheDocument()
    expect(apiMock.mock.calls.some(([path]) => path === '/me/uprawnienia')).toBe(false)
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

    expect(purgeMock).toHaveBeenCalledWith({ reason: 'logout' })
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

    expect(purgeMock).toHaveBeenCalledWith({ reason: 'unauthorized' })
  })

  it('423 WORKSTATION_LOCKED zatrzaskuje ekran i purge tylko raz, zachowując token', async () => {
    apiMock.mockResolvedValue({
      id: 7,
      login: 'manager',
      rola: 'szef',
      uprawnienia: ['rezerwacje.operacje'],
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(authHandlers.workstationLocked).toEqual(expect.any(Function)))

    act(() => authHandlers.workstationLocked())
    act(() => authHandlers.workstationLocked())

    expect(purgeMock).toHaveBeenCalledWith({
      reason: 'workstation-locked',
      preserveSafeRoute: true,
    })
    expect(setTokenMock).not.toHaveBeenCalledWith(null)
    expect(purgeMock).toHaveBeenCalledTimes(1)
    expect(screen.getByText('stanowisko-locked')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź stanowisko' }))
    expect(await screen.findByText('stanowisko-open')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('po credential transition w innej karcie natychmiast odrzuca stary snapshot i pobiera nowego operatora', async () => {
    let currentUser = {
      id: 7,
      login: 'admin-stary',
      rola: 'admin',
      uprawnienia: ['rezerwacje.operacje'],
    }
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') return Promise.resolve(currentUser)
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('operator-admin-stary')).toBeInTheDocument()

    currentUser = {
      id: 8,
      login: 'recepcja-nowa',
      rola: 'employee',
      uprawnienia: ['rezerwacje.operacje'],
    }
    act(() => privacyState.callback?.({ reason: 'login', external: true }))

    expect(screen.getByText('operator-brak')).toBeInTheDocument()
    expect(await screen.findByText('operator-recepcja-nowa')).toBeInTheDocument()
    expect(clearSessionTokenMock).toHaveBeenCalledOnce()
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('external login bez persistent tokenu czyści sesję karty i nie odtwarza starego operatora', async () => {
    getPersistentTokenMock.mockReturnValue(null)
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') {
        return Promise.resolve({
          id: 7,
          login: 'operator-sesyjny',
          rola: 'szef',
          uprawnienia: ['rezerwacje.operacje'],
        })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('operator-operator-sesyjny')).toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'login', external: true }))

    expect(clearSessionTokenMock).toHaveBeenCalledOnce()
    expect(await screen.findByText('operator-brak')).toBeInTheDocument()
    expect(screen.getByText('sesja-ready')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(1)
  })

  it('external logout usuwa także token sesyjny bieżącej karty', async () => {
    apiMock.mockResolvedValue({
      id: 7,
      login: 'operator-sesyjny',
      rola: 'szef',
      uprawnienia: ['rezerwacje.operacje'],
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('operator-operator-sesyjny')).toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'logout', external: true }))

    expect(setTokenMock).toHaveBeenCalledWith(null)
    expect(screen.getByText('operator-brak')).toBeInTheDocument()
  })

  it('lokalna zmiana instancji unieważnia auth snapshot i token', async () => {
    apiMock.mockResolvedValue({
      id: 7,
      login: 'operator-starej-instancji',
      rola: 'szef',
      uprawnienia: [],
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('operator-operator-starej-instancji')).toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'instance-change', external: false }))

    expect(setTokenMock).toHaveBeenCalledWith(null)
    expect(screen.getByText('operator-brak')).toBeInTheDocument()
  })

  it('spóźnione /auth/me ze startu nie odtwarza operatora po logout', async () => {
    let resolveMe
    apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolveMe = resolve }))
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/auth/me'))

    fireEvent.click(screen.getByRole('button', { name: 'Wyloguj testowo' }))
    await act(async () => {
      resolveMe({ id: 7, login: 'stary-operator', rola: 'admin', uprawnienia: [] })
      await Promise.resolve()
    })

    expect(screen.getByText('operator-brak')).toBeInTheDocument()
    expect(screen.getByText('sesja-ready')).toBeInTheDocument()
  })

  it('spóźnione retry blokady nie odtwarza operatora ani nie zdejmuje nowszego stanu', async () => {
    apiMock.mockResolvedValueOnce({
      id: 7,
      login: 'operator-a',
      rola: 'szef',
      uprawnienia: ['rezerwacje.operacje'],
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('operator-operator-a')).toBeInTheDocument()
    act(() => authHandlers.workstationLocked())

    let resolveRetry
    apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolveRetry = resolve }))
    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź stanowisko' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByRole('button', { name: 'Wyloguj testowo' }))

    await act(async () => {
      resolveRetry({ id: 7, login: 'operator-a', rola: 'szef', uprawnienia: [] })
      await Promise.resolve()
    })

    expect(screen.getByText('operator-brak')).toBeInTheDocument()
    expect(screen.getByText('stanowisko-open')).toBeInTheDocument()
  })

  it.each([
    ['Zaloguj ponownie', '/auth/login'],
    ['Zarejestruj ponownie', '/auth/register'],
  ])('rotuje kontekst po udanym explicit auth: %s', async (buttonName, authPath) => {
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') {
        return Promise.resolve({
          id: 7,
          login: 'manager',
          rola: 'szef',
          uprawnienia: [],
        })
      }
      if (path === authPath) {
        return Promise.resolve({
          access_token: 'nowy-token',
          user: { id: 8, login: 'nowy-manager', rola: 'szef', uprawnienia: [] },
        })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByText('sesja-ready')).toBeInTheDocument())
    purgeMock.mockClear()

    fireEvent.click(screen.getByRole('button', { name: buttonName }))

    await waitFor(() => expect(purgeMock).toHaveBeenCalledWith({ reason: 'login' }))
    expect(setTokenMock).toHaveBeenCalledWith(
      'nowy-token',
      ...(authPath === '/auth/login' ? [true] : []),
    )
  })
})
