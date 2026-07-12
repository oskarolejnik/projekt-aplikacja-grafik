// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, toastMock, authState, privacyState, subscribePurgeMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  toastMock: vi.fn(),
  authState: { isAdmin: false, permissions: [] },
  privacyState: { callback: null },
  subscribePurgeMock: vi.fn((callback) => {
    privacyState.callback = callback
    return () => {
      if (privacyState.callback === callback) privacyState.callback = null
    }
  }),
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    isAdmin: authState.isAdmin,
    can: (permission) => authState.permissions.includes(permission),
  }),
}))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../../lib/reservationPrivacy', () => ({
  subscribeReservationPrivacyPurge: subscribePurgeMock,
}))

import WidokHosta from './WidokHosta'

const reservation = {
  id: 7,
  godz_od: '18:00',
  stolik_id: 3,
  stoliki_dodatkowe: [],
  nazwisko: 'Kowalska',
  liczba_osob: 3,
  status: 'potwierdzona',
  faza_hosta: null,
  gosc: { ma_alergie: true, alergie: 'orzechy', vip: false },
}

const queue = {
  nadchodzace: [reservation],
  na_sali: [],
  zakonczone: [],
  waitlista: [],
  podsumowanie: { nadchodzace: 1, na_sali: 0, coverow_na_sali: 0, zakonczone: 0 },
}

describe('Widok hosta — prywatność', () => {
  beforeEach(() => {
    authState.isAdmin = false
    authState.permissions = []
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/host/kolejka?')) return Promise.resolve(queue)
      if (path === '/stoliki') return Promise.resolve({
        stoliki: [{ id: 3, nazwa: 'T3', pojemnosc: 4, aktywny: true }],
      })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
  })

  afterEach(() => {
    cleanup()
    privacyState.callback = null
    vi.clearAllMocks()
  })

  it('nie ujawnia nazwiska ani alergii bez osobnych uprawnień', async () => {
    render(<WidokHosta />)

    expect(await screen.findByText('Gość')).toBeInTheDocument()
    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
    expect(screen.queryByText(/Alergie/)).not.toBeInTheDocument()
    expect(screen.queryByText('orzechy')).not.toBeInTheDocument()
  })

  it('pokazuje ostrzeżenie o alergii wyłącznie po nadaniu prawa do danych wrażliwych', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe', 'rezerwacje.dane_wrazliwe']
    render(<WidokHosta />)

    expect(await screen.findByText('Kowalska')).toBeInTheDocument()
    expect(screen.getByText('Alergie: orzechy')).toBeInTheDocument()
  })

  it('sadza jednym atomowym żądaniem i blokuje podwójne kliknięcie', async () => {
    let resolveSeat
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/host/kolejka?')) return Promise.resolve(queue)
      if (path === '/stoliki') return Promise.resolve({
        stoliki: [{ id: 3, nazwa: 'T3', pojemnosc: 4, aktywny: true }],
      })
      if (path === '/host/rezerwacja/7/posadz' && method === 'POST') {
        expect(body).toEqual({ stolik_id: null })
        return new Promise((resolve) => { resolveSeat = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })
    render(<WidokHosta />)

    const seat = await screen.findByRole('button', { name: 'Posadź' })
    fireEvent.click(seat)
    expect(await screen.findByRole('button', { name: 'Sadzam…' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Sadzam…' }))
    expect(apiMock.mock.calls.filter(([path]) => path === '/host/rezerwacja/7/posadz')).toHaveLength(1)

    await act(async () => resolveSeat({ ...reservation, faza_hosta: 'posadzony' }))
    await waitFor(() => expect(toastMock).toHaveBeenCalledWith(
      'Posadzono.', 'success', { scope: 'reservations' },
    ))
  })

  it('ignoruje spóźnioną odpowiedź poprzedniego dnia', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    const pending = new Map()
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/host/kolejka?')) {
        return new Promise((resolve) => { pending.set(path, resolve) })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta />)
    const dateInput = screen.getByLabelText('Dzień widoku hosta')
    await waitFor(() => expect(pending.size).toBe(1))
    const firstPath = [...pending.keys()][0]
    fireEvent.change(dateInput, { target: { value: '2030-01-02' } })
    await waitFor(() => expect(pending.has('/host/kolejka?data=2030-01-02')).toBe(true))

    const newer = { ...queue, nadchodzace: [{ ...reservation, id: 8, nazwisko: 'Nowsza' }] }
    await act(async () => pending.get('/host/kolejka?data=2030-01-02')(newer))
    expect(await screen.findByText('Nowsza')).toBeInTheDocument()

    const older = { ...queue, nadchodzace: [{ ...reservation, id: 9, nazwisko: 'Starsza' }] }
    await act(async () => pending.get(firstPath)(older))
    expect(screen.queryByText('Starsza')).not.toBeInTheDocument()
    expect(screen.getByText('Nowsza')).toBeInTheDocument()
    expect(screen.getByLabelText('Dzień widoku hosta')).toHaveValue('2030-01-02')
  })

  it('purge abortuje odczyt kolejki i ignoruje spóźniony snapshot PII', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    let resolveQueue
    let requestSignal
    apiMock.mockImplementation((path, _method, _body, options) => {
      if (path.startsWith('/host/kolejka?')) {
        requestSignal = options.signal
        return new Promise((resolve) => { resolveQueue = resolve })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<WidokHosta />)
    await waitFor(() => expect(requestSignal).toBeInstanceOf(AbortSignal))

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))
    expect(requestSignal.aborted).toBe(true)

    await act(async () => resolveQueue(queue))
    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
  })

  it('pokazuje awarię jako błąd z retry, a nie jako pustą salę', async () => {
    let attempts = 0
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/host/kolejka?')) {
        attempts += 1
        return attempts === 1
          ? Promise.reject(new Error('Brak odpowiedzi serwera.'))
          : Promise.resolve(queue)
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<WidokHosta />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak odpowiedzi serwera.')
    expect(screen.queryByText('Sala pusta.')).not.toBeInTheDocument()
    expect(screen.queryByText('Nikt nie czeka na wejście.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))

    expect(await screen.findByText('Gość')).toBeInTheDocument()
    expect(attempts).toBe(2)
  })

  it('nie przeładowuje starego dnia po zakończeniu sadzania', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    const nextDay = '2030-01-04'
    const newerQueue = {
      ...queue,
      nadchodzace: [{ ...reservation, id: 12, nazwisko: 'Nowy dzień' }],
    }
    let resolveSeat
    const queuePaths = []
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/host/kolejka?')) {
        queuePaths.push(path)
        return Promise.resolve(path.includes(nextDay) ? newerQueue : queue)
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [] })
      if (path === '/host/rezerwacja/7/posadz' && method === 'POST') {
        return new Promise((resolve) => { resolveSeat = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta />)
    fireEvent.click(await screen.findByRole('button', { name: 'Posadź' }))
    fireEvent.change(screen.getByLabelText('Dzień widoku hosta'), { target: { value: nextDay } })
    expect(await screen.findByText('Nowy dzień')).toBeInTheDocument()

    await act(async () => resolveSeat({ ...reservation, faza_hosta: 'posadzony' }))
    expect(screen.getByText('Nowy dzień')).toBeInTheDocument()
    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
    expect(queuePaths).toHaveLength(2)
  })

  it('w trybie kontrolowanym zgłasza zmianę dnia i pobiera dopiero datę podaną przez rodzica', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    const firstDay = '2030-03-01'
    const nextDay = '2030-03-02'
    const onDateChange = vi.fn()
    const paths = []
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/host/kolejka?')) {
        paths.push(path)
        const next = path.includes(nextDay)
        return Promise.resolve({
          ...queue,
          nadchodzace: [{ ...reservation, id: next ? 9 : 8, nazwisko: next ? 'Drugi dzień' : 'Pierwszy dzień' }],
        })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    const { rerender } = render(<WidokHosta date={firstDay} onDateChange={onDateChange} />)
    expect(await screen.findByText('Pierwszy dzień')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Dzień widoku hosta'), { target: { value: nextDay } })
    expect(onDateChange).toHaveBeenCalledWith(nextDay)
    expect(screen.getByLabelText('Dzień widoku hosta')).toHaveValue(firstDay)

    rerender(<WidokHosta date={nextDay} onDateChange={onDateChange} />)
    expect(await screen.findByText('Drugi dzień')).toBeInTheDocument()
    expect(paths).toContain(`/host/kolejka?data=${nextDay}`)
  })

  it('nie pobiera ani nie uruchamia pollingu, gdy jest nieaktywny, i zachowuje ostatnie dane', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval')
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval')
    const { rerender } = render(<WidokHosta active={false} />)

    expect(apiMock).not.toHaveBeenCalled()
    expect(intervalSpy).not.toHaveBeenCalled()

    rerender(<WidokHosta active />)
    expect(await screen.findByText('Gość')).toBeInTheDocument()
    expect(intervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000)
    const callsAfterLoad = apiMock.mock.calls.length

    rerender(<WidokHosta active={false} />)
    expect(screen.getByText('Gość')).toBeInTheDocument()
    expect(clearIntervalSpy).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledTimes(callsAfterLoad)

    intervalSpy.mockRestore()
    clearIntervalSpy.mockRestore()
  })

  it('po purge ignoruje spoznione powodzenie sadzania i nie odtwarza toastu', async () => {
    let resolveSeat
    let mutationSignal
    let queueLoads = 0
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path.startsWith('/host/kolejka?')) {
        queueLoads += 1
        return Promise.resolve(queue)
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [] })
      if (path === '/host/rezerwacja/7/posadz' && method === 'POST') {
        mutationSignal = options.signal
        return new Promise((resolve) => { resolveSeat = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta />)
    fireEvent.click(await screen.findByRole('button', { name: /Posad/ }))
    await waitFor(() => expect(mutationSignal).toBeInstanceOf(AbortSignal))

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))
    expect(mutationSignal.aborted).toBe(true)
    await act(async () => resolveSeat({ ...reservation, faza_hosta: 'posadzony' }))

    expect(toastMock).not.toHaveBeenCalled()
    expect(queueLoads).toBe(1)
  })

  it('po purge ignoruje spozniony blad zmiany fazy i nie odtwarza toastu', async () => {
    let rejectPhase
    let mutationSignal
    const seatedQueue = {
      ...queue,
      nadchodzace: [],
      na_sali: [{ ...reservation, faza_hosta: 'posadzony', minuty_od_posadzenia: 10 }],
    }
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path.startsWith('/host/kolejka?')) return Promise.resolve(seatedQueue)
      if (path === '/stoliki') return Promise.resolve({ stoliki: [] })
      if (path === '/host/rezerwacja/7/faza' && method === 'POST') {
        mutationSignal = options.signal
        return new Promise((_resolve, reject) => { rejectPhase = reject })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta />)
    fireEvent.click(await screen.findByRole('button', { name: 'Rachunek' }))
    await waitFor(() => expect(mutationSignal).toBeInstanceOf(AbortSignal))

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))
    expect(mutationSignal.aborted).toBe(true)
    await act(async () => rejectPhase(new Error('Serwer odrzucil zmiane.')))

    expect(toastMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
