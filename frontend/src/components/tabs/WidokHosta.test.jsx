// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, authState, privacyState, subscribePurgeMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authState: {
    isAdmin: false,
    permissions: [],
    user: { id: 17, login: 'recepcja' },
  },
  privacyState: { callback: null },
  subscribePurgeMock: vi.fn((callback) => {
    privacyState.callback = callback
    return () => {
      if (privacyState.callback === callback) privacyState.callback = null
    }
  }),
}))

vi.mock('../../lib/api', () => ({ api: apiMock, getApiBase: () => '' }))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: authState.user,
    isAdmin: authState.isAdmin,
    can: (permission) => authState.permissions.includes(permission),
  }),
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../../lib/reservationPrivacy', () => ({
  subscribeReservationPrivacyPurge: subscribePurgeMock,
}))

import WidokHosta, { patchSnapshotReservation, visitTiming } from './WidokHosta'

const DAY = '2030-03-01'
const NEXT_DAY = '2030-03-02'
const GENERATED_AT = '2030-03-01T16:55:00.000Z'

const reservation = {
  id: 7,
  data: DAY,
  godz_od: '18:00',
  godz_do: '20:00',
  stolik_id: 3,
  stoliki_dodatkowe: [4],
  nazwisko: 'Kowalska',
  liczba_osob: 6,
  status: 'potwierdzona',
  faza_hosta: null,
  gosc: { ma_alergie: true, alergie: 'orzechy', vip: false },
}

const queue = {
  data: DAY,
  nadchodzace: [reservation],
  na_sali: [],
  zakonczone: [],
  waitlista: [],
  podsumowanie: { nadchodzace: 1, na_sali: 0, coverow_na_sali: 0, zakonczone: 0, waitlista: 0 },
}

const floor = {
  data: DAY,
  sala_id: null,
  sale: [{ id: 1, nazwa: 'Sala główna', aktywna: true, kolejnosc: 0 }],
  strefy: ['Sala główna'],
  stoliki: [
    {
      id: 3, nazwa: 'T3', sala_id: 1, strefa: 'Sala główna', sekcja: 'Okno', pojemnosc: 4,
      aktywny: true, aktywny_w_planie: true, plan_x: 30, plan_y: 45, szerokosc: 14, wysokosc: 14,
      obrot: 0, status: 'potwierdzony', rezerwacje: [reservation], live: null,
    },
    {
      id: 4, nazwa: 'T4', sala_id: 1, strefa: 'Sala główna', sekcja: 'Okno', pojemnosc: 2,
      aktywny: true, aktywny_w_planie: true, plan_x: 66, plan_y: 45, szerokosc: 12, wysokosc: 12,
      obrot: 0, status: 'potwierdzony', rezerwacje: [reservation], live: null,
    },
  ],
  kombinacje: [{ id: 1, nazwa: 'T3 + T4', stoliki: [3, 4], pojemnosc_min: 5, pojemnosc_max: 6, priorytet: 0, kanal: 'oba' }],
  podsumowanie: { bez_rezerwacji: 0, zarezerwowane: 2, wstrzymane: 0, nieaktywne: 0, zajete_live: 0 },
}

const timeline = {
  data: DAY,
  stoly: [
    { id: 3, nazwa: 'T3', sekcja: 'Okno', strefa: 'Sala główna' },
    { id: 4, nazwa: 'T4', sekcja: 'Okno', strefa: 'Sala główna' },
  ],
  godziny: ['17:00', '17:30', '18:00', '18:30', '19:00', '19:30', '20:00'],
  zajetosci: [3, 4].map((tableId) => ({
    stolik_id: tableId,
    godz_od: '18:00',
    godz_do: '20:00',
    rezerwacja_id: 7,
    nazwisko: 'Kowalska',
    liczba_osob: 6,
    faza_hosta: null,
  })),
}

const makeSnapshot = ({ day = DAY, nextQueue = queue, nextFloor = floor, nextTimeline = timeline, generatedAt = GENERATED_AT } = {}) => ({
  schema_version: 1,
  version: generatedAt,
  data: day,
  generated_at: generatedAt,
  kolejka: { ...nextQueue, data: day },
  plan_sali: { ...nextFloor, data: day },
  os_czasu: { ...nextTimeline, data: day },
})

const setOnline = (value) => Object.defineProperty(window.navigator, 'onLine', {
  configurable: true,
  value,
})

const setVisibility = (value) => Object.defineProperty(document, 'visibilityState', {
  configurable: true,
  value,
})

describe('Widok hosta R6b.1', () => {
  beforeEach(() => {
    vi.useRealTimers()
    window.sessionStorage.clear()
    window.localStorage.clear()
    setOnline(true)
    setVisibility('visible')
    authState.isAdmin = false
    authState.permissions = []
    authState.user = { id: 17, login: 'recepcja' }
    apiMock.mockImplementation((path) => {
      if (path === `/host/snapshot?data=${DAY}`) return Promise.resolve(makeSnapshot())
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
  })

  afterEach(() => {
    cleanup()
    privacyState.callback = null
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it('zasila plan, listę i oś czasu jednym snapshotem', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    render(<WidokHosta date={DAY} />)

    expect((await screen.findAllByText('Kowalska')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('heading', { name: 'Plan sali' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Oś czasu' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /T3, 4 miejsca, Nadchodząca, Kowalska/ })).toHaveLength(1)
    expect(screen.getByLabelText('T3: Kowalska · 18:00–20:00, 6 osób')).toBeInTheDocument()
    expect(apiMock.mock.calls.filter(([path]) => path.startsWith('/host/snapshot?'))).toHaveLength(1)
    expect(apiMock.mock.calls.some(([path]) => path === '/stoliki' || path.startsWith('/host/kolejka'))).toBe(false)
  })

  it('nie ujawnia nazwiska ani alergii bez osobnych uprawnień', async () => {
    render(<WidokHosta date={DAY} />)

    expect((await screen.findAllByText('Gość')).length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
    expect(screen.queryByText(/Alergie/)).not.toBeInTheDocument()
    expect(screen.queryByText('orzechy')).not.toBeInTheDocument()
  })

  it('pokazuje alergię wyłącznie po nadaniu prawa do danych wrażliwych', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe', 'rezerwacje.dane_wrazliwe']
    render(<WidokHosta date={DAY} />)

    expect((await screen.findAllByText('Kowalska')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Alergie: orzechy')).toBeInTheDocument()
  })

  it('sadza atomowo, blokuje duplikat i lokalnie aktualizuje trzy projekcje', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    let resolveSeat
    let snapshotLoads = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotLoads += 1
        if (snapshotLoads === 1) return Promise.resolve(makeSnapshot())
        return new Promise(() => {})
      }
      if (path === '/host/rezerwacja/7/posadz' && method === 'POST') {
        expect(body).toEqual({ stolik_id: null })
        return new Promise((resolve) => { resolveSeat = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })
    render(<WidokHosta date={DAY} />)

    const seat = await screen.findByRole('button', { name: 'Posadź' })
    fireEvent.click(seat)
    const pending = await screen.findByRole('button', { name: 'Sadzam…' })
    expect(pending).toBeDisabled()
    fireEvent.click(pending)
    expect(apiMock.mock.calls.filter(([path]) => path === '/host/rezerwacja/7/posadz')).toHaveLength(1)

    await act(async () => resolveSeat({ ...reservation, faza_hosta: 'posadzony', minuty_od_posadzenia: 0 }))

    expect(await screen.findByText('Posadzono gości. Widok synchronizuje się w tle.')).toBeInTheDocument()
    expect(screen.getByText('0 min na sali')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /T3, 4 miejsca, Na sali, Kowalska, 0 min/ })).toBeInTheDocument()
    expect(screen.getByLabelText('T3: Kowalska · 18:00–20:00, 6 osób')).toBeInTheDocument()
    expect(screen.queryByLabelText('Ładowanie serwisu')).not.toBeInTheDocument()
  })

  it('zachowuje wybór stołu po błędzie i pozwala ponowić akcję lokalnie', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    let attempts = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path === `/host/snapshot?data=${DAY}`) return Promise.resolve(makeSnapshot())
      if (path === '/host/rezerwacja/7/posadz' && method === 'POST') {
        attempts += 1
        expect(body).toEqual({ stolik_id: 4 })
        const conflict = new Error('Stół został właśnie zajęty.')
        conflict.status = 409
        return attempts === 1
          ? Promise.reject(conflict)
          : Promise.resolve({ ...reservation, stolik_id: 4, stoliki_dodatkowe: [], faza_hosta: 'posadzony', minuty_od_posadzenia: 0 })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)

    const select = await screen.findByLabelText('Stół dla Kowalska')
    fireEvent.change(select, { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Posadź' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Stół został właśnie zajęty.')
    expect(select).toHaveValue('4')
    const retryButton = within(screen.getByRole('alert')).getByRole('button', { name: 'Ponów' })
    await waitFor(() => expect(retryButton).toBeEnabled())
    fireEvent.click(retryButton)
    await waitFor(() => expect(attempts).toBe(2))
    expect(await screen.findByText('Posadzono gości. Widok synchronizuje się w tle.')).toBeInTheDocument()
  })

  it('ignoruje spóźniony snapshot poprzedniego dnia', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    const pending = new Map()
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/host/snapshot?')) {
        return new Promise((resolve) => { pending.set(path, resolve) })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    const onDateChange = vi.fn()
    const { rerender } = render(<WidokHosta date={DAY} onDateChange={onDateChange} />)
    await waitFor(() => expect(pending.has(`/host/snapshot?data=${DAY}`)).toBe(true))

    fireEvent.change(screen.getByLabelText('Dzień widoku hosta'), { target: { value: NEXT_DAY } })
    expect(onDateChange).toHaveBeenCalledWith(NEXT_DAY)
    rerender(<WidokHosta date={NEXT_DAY} onDateChange={onDateChange} />)
    await waitFor(() => expect(pending.has(`/host/snapshot?data=${NEXT_DAY}`)).toBe(true))

    const nextReservation = { ...reservation, id: 8, data: NEXT_DAY, nazwisko: 'Nowa' }
    const nextQueue = { ...queue, data: NEXT_DAY, nadchodzace: [nextReservation] }
    await act(async () => pending.get(`/host/snapshot?data=${NEXT_DAY}`)(makeSnapshot({ day: NEXT_DAY, nextQueue })))
    expect((await screen.findAllByText('Nowa')).length).toBeGreaterThanOrEqual(1)

    await act(async () => pending.get(`/host/snapshot?data=${DAY}`)(makeSnapshot()))
    const queueSection = screen.getByRole('heading', { name: 'Goście' }).closest('section')
    expect(within(queueSection).queryByText('Kowalska')).not.toBeInTheDocument()
    expect(within(queueSection).getByText('Nowa')).toBeInTheDocument()
  })

  it('purge abortuje odczyt i natychmiast usuwa snapshot PII', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    let requestSignal
    let resolveSnapshot
    apiMock.mockImplementation((path, _method, _body, options) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        requestSignal = options.signal
        return new Promise((resolve) => { resolveSnapshot = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)
    await waitFor(() => expect(requestSignal).toBeInstanceOf(AbortSignal))

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))
    expect(requestSignal.aborted).toBe(true)
    await act(async () => resolveSnapshot(makeSnapshot()))
    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
  })

  it('pierwszą awarię pokazuje jako błąd z retry, nie pustą salę', async () => {
    let attempts = 0
    apiMock.mockImplementation((path) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        attempts += 1
        return attempts === 1 ? Promise.reject(new Error('Brak odpowiedzi serwera.')) : Promise.resolve(makeSnapshot())
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak odpowiedzi serwera.')
    expect(screen.queryByText('Spokojny serwis')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))
    expect((await screen.findAllByText('Gość')).length).toBeGreaterThanOrEqual(1)
    expect(attempts).toBe(2)
  })

  it('utrata sieci podczas pierwszego odczytu kończy skeleton i pokazuje bezpieczny błąd', async () => {
    let requestSignal
    apiMock.mockImplementation((path, _method, _body, options) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        requestSignal = options.signal
        return new Promise(() => {})
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)
    await waitFor(() => expect(requestSignal).toBeInstanceOf(AbortSignal))

    setOnline(false)
    act(() => window.dispatchEvent(new Event('offline')))

    expect(requestSignal.aborted).toBe(true)
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia i zapisanego podglądu dla tego dnia.')
    expect(screen.queryByLabelText('Ładowanie serwisu')).not.toBeInTheDocument()
  })

  it('nie pobiera ani nie polluje, gdy widok jest nieaktywny, i zachowuje snapshot po ukryciu', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval')
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval')
    const { rerender } = render(<WidokHosta date={DAY} active={false} />)
    expect(apiMock).not.toHaveBeenCalled()
    expect(intervalSpy).not.toHaveBeenCalled()

    rerender(<WidokHosta date={DAY} active />)
    expect((await screen.findAllByText('Gość')).length).toBeGreaterThanOrEqual(1)
    expect(intervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000)
    const callsAfterLoad = apiMock.mock.calls.length

    rerender(<WidokHosta date={DAY} active={false} />)
    expect(screen.getAllByText('Gość').length).toBeGreaterThanOrEqual(1)
    expect(clearIntervalSpy).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledTimes(callsAfterLoad)
    intervalSpy.mockRestore()
    clearIntervalSpy.mockRestore()
  })

  it('zatrzymuje odczyt w ukrytej karcie i odświeża natychmiast po powrocie', async () => {
    let calls = 0
    apiMock.mockImplementation((path) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        calls += 1
        return Promise.resolve(makeSnapshot())
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)
    expect((await screen.findAllByText('Gość')).length).toBeGreaterThanOrEqual(1)
    expect(calls).toBe(1)

    setVisibility('hidden')
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    await act(async () => {})
    expect(calls).toBe(1)

    setVisibility('visible')
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    await waitFor(() => expect(calls).toBe(2))
  })

  it('po utracie sieci przywraca zanonimizowany cache i bezwzględnie blokuje zapisy', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe', 'rezerwacje.dane_wrazliwe']
    const first = render(<WidokHosta date={DAY} />)
    expect((await screen.findAllByText('Kowalska')).length).toBeGreaterThanOrEqual(1)
    await waitFor(() => expect(window.sessionStorage.length).toBeGreaterThan(0))
    first.unmount()
    apiMock.mockClear()
    setOnline(false)

    render(<WidokHosta date={DAY} />)
    expect((await screen.findAllByText('Gość')).length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
    expect(screen.queryByText('orzechy')).not.toBeInTheDocument()
    expect(screen.getByText('Tylko podgląd')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Posadź' })).toBeDisabled()
    expect(apiMock).not.toHaveBeenCalled()
  })

  it('po powrocie sieci odblokowuje akcje dopiero po pobraniu świeżego snapshotu', async () => {
    let snapshotCalls = 0
    let resolveReconnect
    apiMock.mockImplementation((path) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotCalls += 1
        return snapshotCalls === 1
          ? Promise.resolve(makeSnapshot())
          : new Promise((resolve) => { resolveReconnect = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)
    const seat = await screen.findByRole('button', { name: 'Posadź' })
    expect(seat).toBeEnabled()

    setOnline(false)
    act(() => window.dispatchEvent(new Event('offline')))
    expect(seat).toBeDisabled()

    setOnline(true)
    act(() => window.dispatchEvent(new Event('online')))
    await waitFor(() => expect(resolveReconnect).toBeTypeOf('function'))
    expect(seat).toBeDisabled()

    await act(async () => resolveReconnect(makeSnapshot({ generatedAt: '2030-03-01T16:56:00.000Z' })))
    await waitFor(() => expect(seat).toBeEnabled())
  })

  it('po zerwaniu połączenia podczas zapisu nie udaje porażki ani nie pozwala dublować akcji', async () => {
    apiMock.mockImplementation((path, method) => {
      if (path === `/host/snapshot?data=${DAY}`) return Promise.resolve(makeSnapshot())
      if (path === '/host/rezerwacja/7/posadz' && method === 'POST') {
        return Promise.reject(new TypeError('Failed to fetch'))
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Posadź' }))

    const message = await screen.findByText('Połączenie zostało przerwane. Nie znamy wyniku — odśwież widok przed ponowieniem.')
    expect(within(message.parentElement).queryByRole('button', { name: 'Ponów' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Posadź' })).toBeDisabled()
    expect(apiMock.mock.calls.filter(([path]) => path === '/host/rezerwacja/7/posadz')).toHaveLength(1)
  })

  it('lokalna zmiana fazy nie blankuje widoku, a purge odrzuca spóźnioną odpowiedź', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    const seated = { ...reservation, faza_hosta: 'posadzony', minuty_od_posadzenia: 10 }
    const seatedQueue = {
      ...queue,
      nadchodzace: [],
      na_sali: [seated],
      podsumowanie: { nadchodzace: 0, na_sali: 1, coverow_na_sali: 6, zakonczone: 0, waitlista: 0 },
    }
    let resolvePhase
    let mutationSignal
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path === `/host/snapshot?data=${DAY}`) return Promise.resolve(makeSnapshot({ nextQueue: seatedQueue }))
      if (path === '/host/rezerwacja/7/faza' && method === 'POST') {
        mutationSignal = options.signal
        return new Promise((resolve) => { resolvePhase = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })
    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Rachunek' }))
    await waitFor(() => expect(mutationSignal).toBeInstanceOf(AbortSignal))
    expect(screen.queryByLabelText('Ładowanie serwisu')).not.toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))
    expect(mutationSignal.aborted).toBe(true)
    await act(async () => resolvePhase({ ...seated, faza_hosta: 'rachunek' }))
    expect(screen.queryByText('Etap wizyty zaktualizowany.')).not.toBeInTheDocument()
    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
  })

  it('czyste selektory przenoszą kombinację między listą, planem i timeline', () => {
    const seated = { ...reservation, faza_hosta: 'posadzony', minuty_od_posadzenia: 0 }
    const patched = patchSnapshotReservation(makeSnapshot(), seated)

    expect(patched.kolejka.nadchodzace).toHaveLength(0)
    expect(patched.kolejka.na_sali).toEqual([expect.objectContaining({ id: 7, faza_hosta: 'posadzony' })])
    expect(patched.os_czasu.zajetosci).toEqual(expect.arrayContaining([
      expect.objectContaining({ stolik_id: 3, faza_hosta: 'posadzony' }),
      expect.objectContaining({ stolik_id: 4, faza_hosta: 'posadzony' }),
    ]))
  })

  it('timer opisuje opóźnienie tekstem, nie tylko kolorem', () => {
    const now = new Date('2030-03-01T19:30:00+01:00').getTime()
    expect(visitTiming({ ...reservation, godz_do: '19:15', minuty_od_posadzenia: 70 }, DAY, now)).toEqual({
      text: '15 min po planie',
      className: 'text-danger',
    })
  })
})
