// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, confirmMock, authState, privacyState, subscribePurgeMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  authState: { isAdmin: true, permissions: [] },
  privacyState: { callback: null },
  subscribePurgeMock: vi.fn((callback) => {
    privacyState.callback = callback
    return () => {
      if (privacyState.callback === callback) privacyState.callback = null
    }
  }),
}))

vi.mock('../../lib/api', () => ({
  api: apiMock,
  nowyKluczIdempotencji: () => 'manual-reservation-test-key',
}))
vi.mock('../ui/Toast', () => ({
  useToast: () => ({ confirm: confirmMock, toast: vi.fn() }),
}))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    isAdmin: authState.isAdmin,
    can: (permission) => authState.permissions.includes(permission),
  }),
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../../lib/reservationPrivacy', () => ({
  subscribeReservationPrivacyPurge: subscribePurgeMock,
}))

import RezerwacjeStolik from './RezerwacjeStolik'

const localDateISO = () => {
  const today = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
}

const TEST_DATE = localDateISO()

const TABLE = {
  id: 3,
  nazwa: 'T3',
  strefa: 'Sala',
  pojemnosc: 4,
  aktywny: true,
  kolejnosc: 0,
  rewir_nr: null,
}

const RESERVATION = {
  id: 7,
  data: TEST_DATE,
  godz_od: '18:00',
  godz_do: '20:00',
  stolik_id: TABLE.id,
  stoliki_dodatkowe: [],
  nazwisko: 'Nowak',
  telefon: '500 600 700',
  email: 'nowak@example.com',
  liczba_osob: 3,
  notatka: null,
  status: 'rezerwacja',
  zadatek: 0,
  kanal: 'reczna',
}

const WAITLIST_ENTRY = {
  id: 11,
  data: TEST_DATE,
  godz_od: '19:00',
  liczba_osob: 2,
  nazwisko: 'Kowalska',
  telefon: '501 222 333',
  status: 'oczekuje',
}

function mockInitial({ reservations = [], tables = [TABLE], waitlist = [] } = {}) {
  apiMock.mockImplementation((path) => {
    if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: reservations })
    if (path === '/stoliki') return Promise.resolve({ stoliki: tables })
    if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: waitlist })
    if (path === '/rezerwacje/config') return Promise.resolve({ sale: ['Sala', 'Taras'] })
    return Promise.reject(new Error(`Nieoczekiwany endpoint: GET ${path}`))
  })
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  confirmMock.mockResolvedValue(true)
  authState.isAdmin = true
  authState.permissions = []
  privacyState.callback = null
})

describe('Rezerwacje stolików', () => {
  it('pokazuje czytelne, dostępne akcje zamiast samych ikon', async () => {
    mockInitial({ reservations: [RESERVATION] })

    render(<RezerwacjeStolik />)

    expect(await screen.findByRole('button', { name: 'Potwierdź' })).toHaveClass('min-h-11')
    expect(screen.getByRole('button', { name: 'Odwołaj' })).toHaveClass('min-h-11')
    expect(screen.getByRole('button', { name: 'Otwórz rezerwację: Nowak' })).toHaveClass('min-h-11')
    expect(screen.getByRole('button', { name: 'Edytuj rezerwację: Nowak' })).toHaveClass('min-h-11')
    expect(screen.getByText(/1 aktywna rezerwacja · 3 gości/)).toBeInTheDocument()
  })

  it('zmienia status lokalnie, nie zasłania listy i blokuje duplikat', async () => {
    let resolveStatus
    let serverReservation = RESERVATION
    let listLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        listLoads += 1
        return Promise.resolve({ rezerwacje: [serverReservation] })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/rezerwacje-stolik/${RESERVATION.id}/status` && method === 'POST') {
        return new Promise((resolve) => { resolveStatus = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Potwierdź' }))

    const pending = await screen.findByRole('button', { name: 'Potwierdzam…' })
    expect(pending).toBeDisabled()
    expect(screen.getByText('Nowak')).toBeInTheDocument()
    expect(screen.queryByLabelText('Ładowanie rezerwacji')).not.toBeInTheDocument()

    serverReservation = { ...RESERVATION, status: 'potwierdzona' }
    await act(async () => resolveStatus(serverReservation))

    expect(await screen.findByText('Potwierdzona')).toBeInTheDocument()
    expect(screen.getByText('Potwierdzono rezerwację.')).toBeInTheDocument()
    await waitFor(() => expect(listLoads).toBe(2))
  })

  it('zachowuje formularz po błędzie i po retry dodaje rezerwację bez pełnego przeładowania', async () => {
    let attempts = 0
    let listLoads = 0
    const idempotencyKeys = []
    apiMock.mockImplementation((path, method, body, options) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        listLoads += 1
        return Promise.resolve({ rezerwacje: [] })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === '/rezerwacje-stolik' && method === 'POST') {
        idempotencyKeys.push(options?.headers?.['Idempotency-Key'])
        attempts += 1
        return attempts === 1
          ? Promise.reject(new Error('Brak połączenia.'))
          : Promise.resolve({ ...RESERVATION, ...body, id: 21, godz_do: '20:00', status: 'potwierdzona' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    const name = screen.getByLabelText('Nazwisko / klient')
    fireEvent.change(name, { target: { value: 'Wiśniewska' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia.')
    expect(screen.getByRole('dialog', { name: 'Nowa rezerwacja' })).toBeInTheDocument()
    expect(name).toHaveValue('Wiśniewska')

    fireEvent.click(screen.getByRole('button', { name: 'Ponów zapis' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByText('Wiśniewska')).toBeInTheDocument()
    expect(screen.getByText(/Dodano: Wiśniewska/)).toBeInTheDocument()
    expect(attempts).toBe(2)
    expect(idempotencyKeys).toEqual([
      'manual-reservation-test-key',
      'manual-reservation-test-key',
    ])
    expect(listLoads).toBe(1)
  })

  it('ostrzega przed utratą zmian i po zamknięciu oddaje fokus', async () => {
    mockInitial()
    confirmMock.mockResolvedValue(false)

    render(<RezerwacjeStolik />)
    const trigger = await screen.findByRole('button', { name: 'Dodaj rezerwację' })
    fireEvent.click(trigger)
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Zieliński' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij edycję rezerwacji' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Odrzucić niezapisane zmiany'),
      expect.objectContaining({ confirmText: 'Odrzuć zmiany' }),
    ))
    expect(screen.getByRole('dialog', { name: 'Nowa rezerwacja' })).toBeInTheDocument()

    confirmMock.mockResolvedValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('realizuje wpis z listy oczekujących w miejscu i natychmiast dodaje rezerwację', async () => {
    let resolveSeat
    let listLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        listLoads += 1
        return Promise.resolve({ rezerwacje: [] })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/zrealizuj` && method === 'POST') {
        return new Promise((resolve) => { resolveSeat = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Oczekujący (1)' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Stolik dla Kowalska' }), { target: { value: String(TABLE.id) } })
    fireEvent.click(screen.getByRole('button', { name: 'Posadź' }))

    expect(await screen.findByRole('button', { name: 'Sadzam…' })).toBeDisabled()
    const seatedEntry = { ...WAITLIST_ENTRY, status: 'zrealizowany', termin_id: 31 }
    const createdReservation = { ...RESERVATION, id: 31, nazwisko: WAITLIST_ENTRY.nazwisko, status: 'potwierdzona' }
    await act(async () => resolveSeat({ wpis: seatedEntry, rezerwacja: createdReservation }))

    expect(await screen.findByText('Posadzony')).toBeInTheDocument()
    expect(screen.getByText('Posadzono gości i utworzono rezerwację.')).toBeInTheDocument()
    expect(screen.getAllByText('Kowalska').length).toBeGreaterThan(1)
    expect(listLoads).toBe(1)
  })

  it('prowadzi do wersjonowanej konfiguracji sal zamiast martwego modalu stolików', async () => {
    mockInitial()
    const onOpenRooms = vi.fn()

    render(<RezerwacjeStolik onOpenRooms={onOpenRooms} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Konfiguruj sale' }))

    expect(onOpenRooms).toHaveBeenCalledOnce()
    expect(screen.queryByRole('dialog', { name: 'Stoliki' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dodaj stolik' })).not.toBeInTheDocument()
    expect(apiMock.mock.calls.some(([path, method]) => (
      path === '/stoliki' && ['POST', 'PUT', 'DELETE'].includes(method)
    ))).toBe(false)
  })

  it('nie uzależnia przejścia do konfiguracji sal od stanu odczytu planu dnia', async () => {
    apiMock.mockRejectedValue(new Error('Brak odpowiedzi serwera.'))
    const onOpenRooms = vi.fn()

    render(<RezerwacjeStolik onOpenRooms={onOpenRooms} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak odpowiedzi serwera.')
    const roomsButton = screen.getByRole('button', { name: 'Konfiguruj sale' })
    expect(roomsButton).toBeEnabled()
    fireEvent.click(roomsButton)
    expect(onOpenRooms).toHaveBeenCalledOnce()
  })

  it('po błędzie pierwszego wczytania pokazuje lokalny retry i blokuje zapis w ciemno', async () => {
    let attempts = 0
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        attempts += 1
        return attempts === 1
          ? Promise.reject(new Error('Brak odpowiedzi serwera.'))
          : Promise.resolve({ rezerwacje: [] })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      return Promise.resolve({})
    })

    render(<RezerwacjeStolik />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak odpowiedzi serwera.')
    expect(screen.getByRole('button', { name: 'Dodaj rezerwację' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))

    expect(await screen.findByText('Brak rezerwacji na ten dzień')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dodaj rezerwację' })).toBeEnabled()
    expect(attempts).toBe(2)
  })

  it('bez danych kontaktowych zostawia bezpieczny podgląd i statusy, ale nie oferuje tworzenia ani edycji', async () => {
    authState.isAdmin = false
    authState.permissions = ['rezerwacje.operacje']
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [{ ...RESERVATION, notatka: 'VIP przy oknie', zadatek: 120 }] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)

    expect(await screen.findByText('Gość')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Konfiguruj sale' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dodaj rezerwację' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Edytuj rezerwację/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Otwórz rezerwację/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Potwierdź' })).toBeInTheDocument()
    expect(screen.queryByText('Nowak')).not.toBeInTheDocument()
    expect(screen.queryByText(RESERVATION.telefon)).not.toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalledWith('/lokal/config')
    expect(apiMock).not.toHaveBeenCalledWith('/rezerwacje/config')

    fireEvent.click(screen.getByRole('button', { name: 'Oczekujący (1)' }))
    expect(screen.queryByText(WAITLIST_ENTRY.telefon)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Telefon')).not.toBeInTheDocument()
    expect(screen.queryByText('Dodaj oczekujących')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: `Usuń z listy oczekujących: ${WAITLIST_ENTRY.nazwisko}` })).not.toBeInTheDocument()
  })

  it('po nadaniu praw przeładowuje zredagowane dane przed odblokowaniem edycji', async () => {
    authState.isAdmin = false
    authState.permissions = ['rezerwacje.operacje']
    let listLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        listLoads += 1
        const visible = authState.permissions.includes('rezerwacje.dane_kontaktowe')
        return Promise.resolve({
          rezerwacje: [visible
            ? { ...RESERVATION, notatka: 'Prawdziwa notatka', zadatek: 120 }
            : { ...RESERVATION, nazwisko: 'Gość', telefon: null, email: null, notatka: null, zadatek: null }],
        })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    const { rerender } = render(<RezerwacjeStolik />)
    expect(await screen.findByText('Gość')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Edytuj rezerwację/ })).not.toBeInTheDocument()

    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.notatki_wewnetrzne',
      'rezerwacje.finanse',
    ]
    rerender(<RezerwacjeStolik />)

    const edit = await screen.findByRole('button', { name: 'Edytuj rezerwację: Nowak' })
    expect(listLoads).toBe(2)
    fireEvent.click(edit)
    expect(screen.getByLabelText('Nazwisko / klient')).toHaveValue('Nowak')
    expect(screen.getByLabelText('Notatka')).toHaveValue('Prawdziwa notatka')
    expect(screen.getByLabelText('Zadatek (zł)')).toHaveValue(120)
  })

  it('zamyka otwarty formularz po zmianie widoczności PII i otwiera go ponownie ze świeżymi danymi', async () => {
    authState.isAdmin = false
    authState.permissions = ['rezerwacje.operacje', 'rezerwacje.dane_kontaktowe']
    let listLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        listLoads += 1
        const full = authState.permissions.includes('rezerwacje.notatki_wewnetrzne')
        return Promise.resolve({
          rezerwacje: [{
            ...RESERVATION,
            notatka: full ? 'Świeża notatka' : null,
            zadatek: full ? 180 : null,
          }],
        })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    const { rerender } = render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj rezerwację: Nowak' }))
    expect(screen.getByRole('dialog', { name: 'Edytuj rezerwację' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Notatka')).not.toBeInTheDocument()

    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.notatki_wewnetrzne',
      'rezerwacje.finanse',
    ]
    rerender(<RezerwacjeStolik />)

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const edit = await screen.findByRole('button', { name: 'Edytuj rezerwację: Nowak' })
    expect(listLoads).toBe(2)
    fireEvent.click(edit)
    expect(screen.getByLabelText('Notatka')).toHaveValue('Świeża notatka')
    expect(screen.getByLabelText('Zadatek (zł)')).toHaveValue(180)
  })

  it('nie przywraca poprzedniego dnia po zakończeniu mutacji statusu', async () => {
    const nextDay = '2030-01-02'
    const nextReservation = { ...RESERVATION, id: 8, data: nextDay, nazwisko: 'Jutrzejsza' }
    let resolveStatus
    const listPaths = []
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        listPaths.push(path)
        return Promise.resolve({
          rezerwacje: path.includes(nextDay) ? [nextReservation] : [RESERVATION],
        })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/rezerwacje-stolik/${RESERVATION.id}/status` && method === 'POST') {
        return new Promise((resolve) => { resolveStatus = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Potwierdź' }))
    fireEvent.change(screen.getByLabelText('Dzień rezerwacji'), { target: { value: nextDay } })
    expect(await screen.findByText('Jutrzejsza')).toBeInTheDocument()

    await act(async () => resolveStatus({ ...RESERVATION, status: 'potwierdzona' }))
    expect(screen.getByText('Jutrzejsza')).toBeInTheDocument()
    expect(screen.queryByText('Nowak')).not.toBeInTheDocument()
    expect(listPaths.filter((path) => path.includes(TEST_DATE))).toHaveLength(1)
  })

  it('kończy wskaźnik cichego odświeżenia po przejściu do nowego dnia', async () => {
    const nextDay = '2030-01-03'
    const nextReservation = { ...RESERVATION, id: 9, data: nextDay, nazwisko: 'Nowy dzień' }
    let oldLoads = 0
    let resolveOldRefresh
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        if (path.includes(nextDay)) return Promise.resolve({ rezerwacje: [nextReservation] })
        oldLoads += 1
        if (oldLoads === 1) return Promise.resolve({ rezerwacje: [RESERVATION] })
        return new Promise((resolve) => { resolveOldRefresh = resolve })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/rezerwacje-stolik/${RESERVATION.id}/status` && method === 'POST') {
        return Promise.resolve({ ...RESERVATION, status: 'potwierdzona' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Potwierdź' }))
    await waitFor(() => expect(oldLoads).toBe(2))
    expect(screen.getByText('Aktualizuję…')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Dzień rezerwacji'), { target: { value: nextDay } })
    expect(await screen.findByText('Nowy dzień')).toBeInTheDocument()
    expect(screen.queryByText('Aktualizuję…')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Potwierdź' })).toBeEnabled()

    await act(async () => resolveOldRefresh({ rezerwacje: [{ ...RESERVATION, nazwisko: 'Stary dzień' }] }))
    expect(screen.getByText('Nowy dzień')).toBeInTheDocument()
    expect(screen.queryByText('Stary dzień')).not.toBeInTheDocument()
  })

  it('po konflikcie pacingu pokazuje świadome przekroczenie tylko z uprawnieniem', async () => {
    authState.isAdmin = false
    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.nadpisuj_limity',
    ]
    let attempts = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje-stolik' && method === 'POST') {
        attempts += 1
        if (attempts === 1) {
          const error = new Error('Osiągnięto limit nowych rezerwacji.')
          error.code = 'PACING_RESERVATION_LIMIT'
          return Promise.reject(error)
        }
        return Promise.resolve({ ...RESERVATION, ...body, id: 55, status: 'potwierdzona' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Limitowana' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByText('Osiągnięto limit nowych rezerwacji.')).toHaveClass('text-lemon')
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz mimo limitu' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const overrideBody = apiMock.mock.calls.filter(
      ([path, method]) => path === '/rezerwacje-stolik' && method === 'POST',
    )[1][2]
    expect(overrideBody.przekrocz_limity).toBe(true)
  })

  it('preset Recepcji zachowuje tworzenie i kontakty, ale ukrywa salę, finanse, notatki i DELETE', async () => {
    authState.isAdmin = false
    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.host',
      'rezerwacje.nadpisuj_limity',
      'rezerwacje.dane_kontaktowe',
    ]
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [{ ...RESERVATION, notatka: 'VIP przy oknie', zadatek: 120 }] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === `/rezerwacje-stolik/${RESERVATION.id}` && method === 'PUT') {
        return Promise.resolve({ ...RESERVATION, ...body, notatka: null, zadatek: null })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)

    expect(await screen.findByRole('button', { name: 'Dodaj rezerwację' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Konfiguruj sale' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Edytuj rezerwację: Nowak' }))
    expect(screen.getByLabelText('Telefon')).toHaveValue(RESERVATION.telefon)
    expect(screen.getByLabelText('E-mail')).toHaveValue(RESERVATION.email)
    expect(screen.queryByLabelText('Notatka')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Zadatek (zł)')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Usuń' })).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Nowak-Kowalski' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      `/rezerwacje-stolik/${RESERVATION.id}`,
      'PUT',
      expect.objectContaining({
        nazwisko: 'Nowak-Kowalski',
        telefon: RESERVATION.telefon,
        email: RESERVATION.email,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    const updateBody = apiMock.mock.calls.find(([path, method]) => path === `/rezerwacje-stolik/${RESERVATION.id}` && method === 'PUT')[2]
    expect(updateBody).not.toHaveProperty('notatka')
    expect(updateBody).not.toHaveProperty('zadatek')
  })

  it('w trybie kontrolowanym zgłasza zmianę dnia i czeka na nową wartość z rodzica', async () => {
    const firstDay = '2030-02-01'
    const nextDay = '2030-02-02'
    const onDateChange = vi.fn()
    const paths = []
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        paths.push(path)
        return Promise.resolve({
          rezerwacje: [{
            ...RESERVATION,
            data: path.includes(nextDay) ? nextDay : firstDay,
            nazwisko: path.includes(nextDay) ? 'Drugi dzień' : 'Pierwszy dzień',
          }],
        })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: GET ${path}`))
    })

    const { rerender } = render(<RezerwacjeStolik date={firstDay} onDateChange={onDateChange} />)
    expect(await screen.findByText('Pierwszy dzień')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Dzień rezerwacji'), { target: { value: nextDay } })
    expect(onDateChange).toHaveBeenCalledWith(nextDay)
    expect(screen.getByLabelText('Dzień rezerwacji')).toHaveValue(firstDay)

    rerender(<RezerwacjeStolik date={nextDay} onDateChange={onDateChange} />)
    expect(await screen.findByText('Drugi dzień')).toBeInTheDocument()
    expect(paths.some((path) => path.includes(`start=${nextDay}&end=${nextDay}`))).toBe(true)
  })

  it('otwiera rezerwację wskazaną zewnętrznym id dopiero z właściwie załadowanego dnia', async () => {
    const onReservationOpen = vi.fn()
    const onReservationClose = vi.fn()
    mockInitial({ reservations: [RESERVATION] })

    const { rerender } = render(
      <RezerwacjeStolik
        date={TEST_DATE}
        reservationId={RESERVATION.id}
        onReservationOpen={onReservationOpen}
        onReservationClose={onReservationClose}
      />,
    )

    expect(await screen.findByRole('dialog', { name: 'Edytuj rezerwację' })).toBeInTheDocument()
    expect(screen.getByLabelText('Nazwisko / klient')).toHaveValue('Nowak')
    expect(onReservationOpen).not.toHaveBeenCalled()

    rerender(
      <RezerwacjeStolik
        date={TEST_DATE}
        reservationId={null}
        onReservationOpen={onReservationOpen}
        onReservationClose={onReservationClose}
      />,
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('przekazuje opaque id do karty gościa i zachowuje szkic podczas zawieszenia dialogu', async () => {
    mockInitial({ reservations: [RESERVATION] })
    const onGuestProfileOpen = vi.fn()
    const props = {
      date: TEST_DATE,
      reservationId: RESERVATION.id,
      onGuestProfileOpen,
    }
    const { rerender } = render(<RezerwacjeStolik {...props} />)

    expect(await screen.findByRole('dialog', { name: 'Edytuj rezerwację' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Szkic przed profilem' } })
    fireEvent.click(screen.getByRole('button', { name: 'Karta gościa' }))

    expect(onGuestProfileOpen).toHaveBeenCalledWith(RESERVATION.id)
    rerender(<RezerwacjeStolik {...props} suspendReservationDialog />)
    expect(screen.queryByRole('dialog', { name: 'Edytuj rezerwację' })).not.toBeInTheDocument()

    rerender(<RezerwacjeStolik {...props} suspendReservationDialog={false} />)
    expect(await screen.findByLabelText('Nazwisko / klient')).toHaveValue('Szkic przed profilem')
  })

  it('nie zamyka niezapisanego formularza po wyczyszczeniu zewnętrznego selection', async () => {
    mockInitial({ reservations: [RESERVATION] })
    const onReservationClose = vi.fn()
    const { rerender } = render(
      <RezerwacjeStolik date={TEST_DATE} reservationId={RESERVATION.id} onReservationClose={onReservationClose} />,
    )
    expect(await screen.findByRole('dialog', { name: 'Edytuj rezerwację' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Niezapisany szkic' } })

    rerender(<RezerwacjeStolik date={TEST_DATE} reservationId={null} onReservationClose={onReservationClose} />)

    expect(screen.getByRole('dialog', { name: 'Edytuj rezerwację' })).toBeInTheDocument()
    expect(screen.getByLabelText('Nazwisko / klient')).toHaveValue('Niezapisany szkic')
  })

  it('zgłasza lokalne otwarcie i zwykłe zamknięcie, ale nie otwiera obcego id', async () => {
    const onReservationOpen = vi.fn()
    const onReservationClose = vi.fn()
    mockInitial({ reservations: [RESERVATION] })
    const { rerender } = render(
      <RezerwacjeStolik onReservationOpen={onReservationOpen} onReservationClose={onReservationClose} />,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj rezerwację: Nowak' }))
    expect(onReservationOpen).toHaveBeenCalledWith(RESERVATION.id)
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij edycję rezerwacji' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(onReservationClose).toHaveBeenCalledTimes(1)

    onReservationClose.mockClear()
    rerender(
      <RezerwacjeStolik
        reservationId={9999}
        onReservationOpen={onReservationOpen}
        onReservationClose={onReservationClose}
      />,
    )
    await waitFor(() => expect(onReservationClose).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('purge abortuje odczyt dnia i ignoruje spóźniony snapshot PII', async () => {
    let resolveReservations
    let requestSignal
    apiMock.mockImplementation((path, _method, _body, options) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        requestSignal = options.signal
        return new Promise((resolve) => { resolveReservations = resolve })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<RezerwacjeStolik />)
    await waitFor(() => expect(requestSignal).toBeInstanceOf(AbortSignal))

    act(() => privacyState.callback?.({ reason: 'logout' }))
    expect(requestSignal.aborted).toBe(true)

    await act(async () => resolveReservations({ rezerwacje: [RESERVATION] }))
    expect(screen.queryByText('Nowak')).not.toBeInTheDocument()
  })

  it('purge podczas pending 409 nie otwiera confirmu ani nie wysyła override', async () => {
    authState.isAdmin = false
    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.nadpisuj_limity',
    ]
    confirmMock.mockResolvedValue(true)
    let rejectSeat
    let mutationSignal
    let mutationAttempts = 0
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/zrealizuj` && method === 'POST') {
        mutationAttempts += 1
        mutationSignal = options.signal
        return new Promise((_resolve, reject) => { rejectSeat = reject })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: /Oczekuj/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Stolik dla Kowalska/ }), {
      target: { value: String(TABLE.id) },
    })
    fireEvent.click(screen.getByRole('button', { name: /Posad/ }))
    await waitFor(() => expect(rejectSeat).toEqual(expect.any(Function)))

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))
    expect(mutationSignal.aborted).toBe(true)
    const conflict = new Error('Osiągnięto limit.')
    conflict.code = 'PACING_RESERVATION_LIMIT'
    await act(async () => rejectSeat(conflict))

    expect(confirmMock).not.toHaveBeenCalled()
    expect(mutationAttempts).toBe(1)
  })
})
