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
  getWorkstationCsrfMock,
  clearWorkstationCsrfMock,
  rotateCredentialGenerationMock,
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
    getWorkstationCsrfMock: vi.fn(),
    clearWorkstationCsrfMock: vi.fn(),
    rotateCredentialGenerationMock: vi.fn(),
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
  getApiBase: () => '',
  getToken: getTokenMock,
  getPersistentToken: getPersistentTokenMock,
  clearSessionToken: clearSessionTokenMock,
  setToken: setTokenMock,
  setUnauthorizedHandler: setUnauthorizedHandlerMock,
  setWorkstationLockedHandler: setWorkstationLockedHandlerMock,
  getWorkstationCsrf: getWorkstationCsrfMock,
  clearWorkstationCsrf: clearWorkstationCsrfMock,
  rotateCredentialGeneration: rotateCredentialGenerationMock,
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
    workstationGate,
    workstationSession,
    workstationIdleWarning,
    unlockWorkstation,
    reauthorizeWorkstation,
    lockWorkstation,
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
      <span>stanowisko-{workstationGate?.station?.name || workstationSession?.station?.name || 'brak'}</span>
      <span>{workstationIdleWarning == null ? 'idle-bez-ostrzeżenia' : `idle-ostrzeżenie-${workstationIdleWarning}`}</span>
      <span>{authorizationRefreshing ? 'autoryzacja-refreshing' : 'autoryzacja-ready'}</span>
      <span>{authorizationError || 'autoryzacja-ok'}</span>
      <button type="button" onClick={() => login('nowy-manager', 'haslo')}>Zaloguj ponownie</button>
      <button type="button" onClick={() => register({ login: 'nowy-manager', haslo: 'haslo' })}>Zarejestruj ponownie</button>
      <button type="button" onClick={logout}>Wyloguj testowo</button>
      <button type="button" onClick={retryWorkstation}>Sprawdź stanowisko</button>
      <button type="button" onClick={() => unlockWorkstation({ userId: 12, pin: '123456' })}>Odblokuj PIN</button>
      <button type="button" onClick={() => reauthorizeWorkstation({ pin: '123456' })}>Potwierdź operację PIN-em</button>
      <button type="button" onClick={() => lockWorkstation()}>Zablokuj stanowisko</button>
    </div>
  )
}

const workstationSessionFixture = ({
  userId = 12,
  login = 'recepcja-ola',
  timeout = 60,
} = {}) => ({
  active: true,
  station: { id: 'desk-1', name: 'Recepcja', idle_timeout_seconds: timeout },
  idle_timeout_seconds: timeout,
  user: {
    id: userId,
    login,
    rola: 'szef',
    uprawnienia: ['rezerwacje.operacje'],
  },
})

describe('AuthContext permissions', () => {
  beforeEach(() => {
    getTokenMock.mockReturnValue('token')
    getPersistentTokenMock.mockReturnValue('token')
    getWorkstationCsrfMock.mockReturnValue(null)
    apiMock.mockReset()
    authHandlers.unauthorized = null
    authHandlers.workstationLocked = null
    privacyState.callback = null
    setUnauthorizedHandlerMock.mockImplementation((handler) => { authHandlers.unauthorized = handler })
    setWorkstationLockedHandlerMock.mockImplementation((handler) => { authHandlers.workstationLocked = handler })
    window.history.replaceState({}, '', '/')
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/')
  })

  it('na dedykowanym adresie wykrywa zarejestrowane stanowisko i pokazuje fail-closed PIN gate', async () => {
    getTokenMock.mockReturnValue(null)
    getPersistentTokenMock.mockReturnValue(null)
    window.history.replaceState({}, '', '/?stanowisko')
    apiMock.mockImplementation((path) => {
      if (path === '/reservation-workstations/operators') return Promise.resolve({
        station: { id: 'desk-1', name: 'Recepcja', idle_timeout_seconds: 300 },
        operators: [{ id: 12, display_name: 'Ola Nowak' }],
      })
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })

    render(<AuthProvider><Probe /></AuthProvider>)

    expect(await screen.findByText('stanowisko-Recepcja')).toBeInTheDocument()
    expect(screen.getByText('stanowisko-locked')).toBeInTheDocument()
    expect(screen.getByText('operator-brak')).toBeInTheDocument()
  })

  it('ustanawia nazwaną sesję PIN bez zapisywania zwykłego bearer tokenu', async () => {
    getTokenMock.mockReturnValue(null)
    getPersistentTokenMock.mockReturnValue(null)
    window.history.replaceState({}, '', '/?stanowisko')
    const gate = {
      station: { id: 'desk-1', name: 'Recepcja', idle_timeout_seconds: 300 },
      operators: [{ id: 12, display_name: 'Ola Nowak' }],
    }
    apiMock.mockImplementation((path, method) => {
      if (path === '/reservation-workstations/operators') return Promise.resolve(gate)
      if (path === '/reservation-workstations/unlock' && method === 'POST') return Promise.resolve({
        active: true,
        station: gate.station,
        idle_timeout_seconds: 300,
        user: {
          id: 12,
          login: 'recepcja-ola',
          rola: 'szef',
          uprawnienia: ['rezerwacje.operacje', 'rezerwacje.host'],
        },
      })
      if (path === '/me/reservation-workstation/reauthorize' && method === 'POST') return Promise.resolve({
        grant: 'wreauth-one-shot',
        scope: 'reservation_override',
        expires_at: '2026-07-18T12:01:30Z',
      })
      if (path === '/me/reservation-workstation/lock' && method === 'POST') return Promise.resolve(null)
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('stanowisko-locked')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Odblokuj PIN' }))

    expect(await screen.findByText('operator-recepcja-ola')).toBeInTheDocument()
    expect(screen.getByText('stanowisko-open')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/reservation-workstations/unlock',
      'POST',
      { operator_id: 12, pin: '123456' },
      { headers: { 'X-Lokalo-Workstation-Intent': 'unlock' } },
    )
    expect(setTokenMock).toHaveBeenCalledWith(null)
    expect(purgeMock).toHaveBeenCalledWith({ reason: 'login' })

    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź operację PIN-em' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/me/reservation-workstation/reauthorize',
      'POST',
      { pin: '123456', scope: 'reservation_override' },
      { headers: { 'X-Lokalo-Workstation-Intent': 'reauthorize' } },
    ))
    expect(setTokenMock).not.toHaveBeenCalledWith('wreauth-one-shot')

    fireEvent.click(screen.getByRole('button', { name: 'Zablokuj stanowisko' }))
    expect(screen.getByText('stanowisko-locked')).toBeInTheDocument()
    expect(screen.getByText('operator-brak')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/me/reservation-workstation/lock',
      'POST',
      { reason: 'manual' },
    )
  })

  it('po odświeżeniu odtwarza aktywną sesję wyłącznie z bezpiecznych cookies', async () => {
    getTokenMock.mockReturnValue(null)
    getPersistentTokenMock.mockReturnValue(null)
    getWorkstationCsrfMock.mockReturnValue('csrf-value')
    apiMock.mockImplementation((path) => {
      if (path === '/me/reservation-workstation') return Promise.resolve({
        active: true,
        station: { id: 'desk-1', name: 'Recepcja', idle_timeout_seconds: 300 },
        idle_timeout_seconds: 300,
        user: {
          id: 12,
          login: 'recepcja-ola',
          rola: 'szef',
          uprawnienia: ['rezerwacje.operacje'],
        },
      })
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })

    render(<AuthProvider><Probe /></AuthProvider>)

    expect(await screen.findByText('operator-recepcja-ola')).toBeInTheDocument()
    expect(screen.getByText('stanowisko-open')).toBeInTheDocument()
    expect(setTokenMock).not.toHaveBeenCalledWith(expect.any(String))
  })

  it('ostrzega 30 sekund przed idle timeoutem i blokuje stanowisko dokładnie raz', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T12:00:00Z'))
    getTokenMock.mockReturnValue(null)
    getPersistentTokenMock.mockReturnValue(null)
    getWorkstationCsrfMock.mockReturnValue('csrf-value')
    const session = workstationSessionFixture({ timeout: 60 })
    apiMock.mockImplementation((path, method) => {
      if (path === '/me/reservation-workstation' && (!method || method === 'GET')) return Promise.resolve(session)
      if (path === '/me/reservation-workstation/lock' && method === 'POST') return new Promise(() => {})
      if (path === '/me/uprawnienia') return Promise.resolve({
        rola: session.user.rola,
        uprawnienia: session.user.uprawnienia,
      })
      return Promise.reject(new Error(`Nieoczekiwane żądanie: ${method || 'GET'} ${path}`))
    })

    render(<AuthProvider><Probe /></AuthProvider>)
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByText('operator-recepcja-ola')).toBeInTheDocument()
    expect(screen.getByText('idle-bez-ostrzeżenia')).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(29_000))
    expect(screen.getByText('idle-bez-ostrzeżenia')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1_000))
    expect(screen.getByText('idle-ostrzeżenie-30')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(29_000))
    expect(screen.getByText('idle-ostrzeżenie-1')).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(1_000))
    expect(screen.getByText('stanowisko-locked')).toBeInTheDocument()
    expect(screen.getByText('operator-brak')).toBeInTheDocument()
    expect(screen.getByText('idle-bez-ostrzeżenia')).toBeInTheDocument()
    expect(purgeMock).toHaveBeenCalledWith({ reason: 'workstation-locked' })
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/lock' && method === 'POST',
    )).toEqual([[
      '/me/reservation-workstation/lock',
      'POST',
      { reason: 'idle' },
    ]])

    act(() => vi.advanceTimersByTime(120_000))
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/lock' && method === 'POST',
    )).toHaveLength(1)
    expect(purgeMock).toHaveBeenCalledTimes(1)
  })

  it('po powrocie karty z tła natychmiast sprawdza idle timeout i maskuje PII', async () => {
    vi.useFakeTimers()
    const startedAt = new Date('2026-07-18T12:00:00Z')
    vi.setSystemTime(startedAt)
    getTokenMock.mockReturnValue(null)
    getPersistentTokenMock.mockReturnValue(null)
    getWorkstationCsrfMock.mockReturnValue('csrf-value')
    const session = workstationSessionFixture({ timeout: 60 })
    apiMock.mockImplementation((path, method) => {
      if (path === '/me/reservation-workstation' && (!method || method === 'GET')) return Promise.resolve(session)
      if (path === '/me/reservation-workstation/lock' && method === 'POST') return new Promise(() => {})
      if (path === '/me/uprawnienia') return Promise.resolve({
        rola: session.user.rola,
        uprawnienia: session.user.uprawnienia,
      })
      return Promise.reject(new Error(`Nieoczekiwane żądanie: ${method || 'GET'} ${path}`))
    })
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')

    render(<AuthProvider><Probe /></AuthProvider>)
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByText('operator-recepcja-ola')).toBeInTheDocument()

    vi.setSystemTime(new Date(startedAt.getTime() + 61_000))
    expect(screen.getByText('operator-recepcja-ola')).toBeInTheDocument()
    visibility.mockReturnValue('visible')
    fireEvent(document, new Event('visibilitychange'))

    expect(screen.getByText('stanowisko-locked')).toBeInTheDocument()
    expect(screen.getByText('operator-brak')).toBeInTheDocument()
    expect(purgeMock).toHaveBeenCalledWith({ reason: 'workstation-locked' })
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/lock' && method === 'POST',
    )).toEqual([[
      '/me/reservation-workstation/lock',
      'POST',
      { reason: 'idle' },
    ]])
  })

  it('throttluje touch do jednego na 30 sekund i czyści idle listenery po zmianie operatora oraz unmount', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T12:00:00Z'))
    getTokenMock.mockReturnValue(null)
    getPersistentTokenMock.mockReturnValue(null)
    getWorkstationCsrfMock.mockReturnValue('csrf-value')
    const initialSession = workstationSessionFixture({ timeout: 60 })
    const replacementSession = workstationSessionFixture({
      userId: 13,
      login: 'recepcja-ewa',
      timeout: 300,
    })
    apiMock.mockImplementation((path, method) => {
      if (path === '/me/reservation-workstation' && (!method || method === 'GET')) return Promise.resolve(initialSession)
      if (path === '/reservation-workstations/unlock' && method === 'POST') return Promise.resolve(replacementSession)
      if (path === '/me/reservation-workstation/touch' && method === 'POST') return Promise.resolve(null)
      if (path === '/me/uprawnienia') return Promise.resolve({
        rola: replacementSession.user.rola,
        uprawnienia: replacementSession.user.uprawnienia,
      })
      if (path === '/me/reservation-workstation/lock' && method === 'POST') return Promise.resolve(null)
      return Promise.reject(new Error(`Nieoczekiwane żądanie: ${method || 'GET'} ${path}`))
    })

    const view = render(<AuthProvider><Probe /></AuthProvider>)
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByText('operator-recepcja-ola')).toBeInTheDocument()

    fireEvent.pointerDown(window)
    fireEvent.keyDown(window, { key: 'A' })
    fireEvent.touchStart(window)
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/touch' && method === 'POST',
    )).toHaveLength(1)

    act(() => vi.advanceTimersByTime(29_999))
    fireEvent.pointerDown(window)
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/touch' && method === 'POST',
    )).toHaveLength(1)
    act(() => vi.advanceTimersByTime(1))
    fireEvent.keyDown(window, { key: 'B' })
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/touch' && method === 'POST',
    )).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: 'Odblokuj PIN' }))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByText('operator-recepcja-ewa')).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(61_000))
    expect(screen.getByText('stanowisko-open')).toBeInTheDocument()
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/lock' && method === 'POST',
    )).toHaveLength(0)

    const touchesBeforeUnmount = apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/touch' && method === 'POST',
    ).length
    view.unmount()
    fireEvent.pointerDown(window)
    fireEvent.keyDown(window, { key: 'C' })
    act(() => vi.advanceTimersByTime(400_000))
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/touch' && method === 'POST',
    )).toHaveLength(touchesBeforeUnmount)
    expect(apiMock.mock.calls.filter(
      ([path, method]) => path === '/me/reservation-workstation/lock' && method === 'POST',
    )).toHaveLength(0)
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

  it('423 WORKSTATION_LOCKED zatrzaskuje ekran, czyści PII tylko raz i pobiera PIN gate', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') return Promise.resolve({
        id: 7,
        login: 'manager',
        rola: 'szef',
        uprawnienia: ['rezerwacje.operacje'],
      })
      if (path === '/reservation-workstations/operators') return Promise.resolve({
        station: { id: 'desk-1', name: 'Recepcja' },
        operators: [],
      })
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(authHandlers.workstationLocked).toEqual(expect.any(Function)))

    act(() => authHandlers.workstationLocked())
    act(() => authHandlers.workstationLocked())

    expect(purgeMock).toHaveBeenCalledWith({ reason: 'workstation-locked' })
    expect(setTokenMock).not.toHaveBeenCalledWith(null)
    expect(purgeMock).toHaveBeenCalledTimes(1)
    expect(screen.getByText('stanowisko-locked')).toBeInTheDocument()

    expect(apiMock.mock.calls.some(([path]) => path === '/reservation-workstations/operators')).toBe(true)
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

  it('spóźnione pobranie PIN gate nie przywraca blokady po nowszym logout', async () => {
    let resolveGate
    apiMock.mockImplementation((path) => {
      if (path === '/auth/me') return Promise.resolve({
        id: 7,
        login: 'operator-a',
        rola: 'szef',
        uprawnienia: ['rezerwacje.operacje'],
      })
      if (path === '/reservation-workstations/operators') {
        return new Promise((resolve) => { resolveGate = resolve })
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    render(<AuthProvider><Probe /></AuthProvider>)
    expect(await screen.findByText('operator-operator-a')).toBeInTheDocument()
    act(() => authHandlers.workstationLocked())
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByRole('button', { name: 'Wyloguj testowo' }))

    await act(async () => {
      resolveGate({ station: { id: 'desk-1' }, operators: [] })
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
