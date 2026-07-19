// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const {
  apiMock,
  confirmMock,
  reauthorizeWorkstationMock,
  authState,
  privacyState,
  subscribePurgeMock,
} = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  reauthorizeWorkstationMock: vi.fn(),
  authState: { isAdmin: true, permissions: [], workstationSession: null },
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
    workstationSession: authState.workstationSession,
    reauthorizeWorkstation: reauthorizeWorkstationMock,
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
  kanal_komunikacji: 'auto',
  communication_summary: null,
}

const WAITLIST_ENTRY = {
  id: 11,
  data: TEST_DATE,
  godz_od: '19:00',
  liczba_osob: 2,
  nazwisko: 'Kowalska',
  telefon: '501 222 333',
  email: null,
  kanal_komunikacji: 'auto',
  communication_summary: null,
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
  authState.workstationSession = null
  reauthorizeWorkstationMock.mockReset()
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

  it('pokazuje stan komunikacji w Dzisiaj', async () => {
    const reservation = {
      ...RESERVATION,
      communication_summary: {
        state: 'sent',
        channel: 'email',
        event: 'confirmation',
        attention_required: false,
        attention_count: 0,
      },
    }
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [reservation] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)

    expect(await screen.findByLabelText('Wysłano, e-mail')).toBeInTheDocument()
  })

  it('zapisuje preferencję kanału w formularzu rezerwacji', async () => {
    let createBody
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje-stolik' && method === 'POST') {
        createBody = body
        return Promise.resolve({ ...RESERVATION, ...body, id: 72 })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'SMS Gość' } })
    fireEvent.change(screen.getByLabelText('Telefon'), { target: { value: '500600700' } })
    fireEvent.change(screen.getByLabelText('Kanał komunikacji'), { target: { value: 'sms' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => expect(createBody).toEqual(expect.objectContaining({
      kanal_komunikacji: 'sms',
      telefon: '500600700',
    })))
  })

  it('jawnie proponuje przydział i czyści stary wynik po zmianie trybu lub terminu', async () => {
    let resolveSimulation
    const simulation = {
      decision: 'allow',
      available: true,
      visit_end: '20:00',
      allocation: {
        state: 'preview',
        visibility: 'exact',
        room: { id: 2, name: 'Sala Główna' },
        tables: [{ id: 4, name: 'S1', capacity: 4 }, { id: 5, name: 'S2', capacity: 2 }],
        capacity: 6,
        reasons: [{ code: 'TABLES_ADJACENT', message: 'Stoły sąsiadują' }],
      },
      alternatives: [{ kind: 'time', time: '18:30' }],
    }
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/reguly/symuluj' && method === 'POST') {
        expect(body).toEqual({
          data: TEST_DATE,
          godz_od: '18:00',
          liczba_osob: 6,
          kanal: 'wewnetrzna',
          sala_id: null,
        })
        return new Promise((resolve) => { resolveSimulation = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    fireEvent.change(screen.getByLabelText('Liczba osób'), { target: { value: '6' } })
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Kowalska' } })

    const suggest = screen.getByRole('button', { name: 'Zaproponuj przydział' })
    expect(suggest).toHaveClass('min-h-11')
    fireEvent.click(suggest)
    expect(await screen.findByRole('button', { name: 'Proponuję przydział…' })).toBeDisabled()

    await act(async () => resolveSimulation(simulation))

    expect(await screen.findByText('Sala Główna · S1 + S2')).toBeInTheDocument()
    expect(screen.getByText('6 miejsc · do 20:00')).toBeInTheDocument()
    expect(screen.getByText('Stoły sąsiadują')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż 1 alternatywę' }))
    expect(screen.getByText('18:30')).toBeInTheDocument()
    expect(screen.getByLabelText('Nazwisko / klient')).toHaveValue('Kowalska')

    fireEvent.click(screen.getByRole('button', { name: 'Walk-in (gość na miejscu)' }))
    expect(screen.queryByText('Sala Główna · S1 + S2')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Nazwisko / klient')).toHaveValue('Kowalska')

    fireEvent.click(screen.getByRole('button', { name: 'Rezerwacja' }))
    fireEvent.click(screen.getByRole('button', { name: 'Zaproponuj przydział' }))
    await act(async () => resolveSimulation(simulation))
    expect(await screen.findByText('Sala Główna · S1 + S2')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Godzina'), { target: { value: '19:00' } })
    expect(screen.queryByText('Sala Główna · S1 + S2')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Nazwisko / klient')).toHaveValue('Kowalska')
  })

  it('po potwierdzonym braku przydziału przenosi szkic na waitlistę bez przepisywania danych', async () => {
    let waitlistBody
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/reguly/symuluj' && method === 'POST') {
        return Promise.resolve({
          decision: 'deny',
          available: false,
          allocation: null,
          violations: [{ code: 'NO_CAPACITY_MATCH', message: 'Brak zestawu dla 6 osób.' }],
        })
      }
      if (path === '/lista-oczekujacych' && method === 'POST') {
        waitlistBody = body
        return Promise.resolve({ ...WAITLIST_ENTRY, ...body, id: 42 })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    const reservationTrigger = await screen.findByRole('button', { name: 'Dodaj rezerwację' })
    fireEvent.click(reservationTrigger)
    fireEvent.change(screen.getByLabelText('Liczba osób'), { target: { value: '6' } })
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Kowalska' } })
    fireEvent.change(screen.getByLabelText('Telefon'), { target: { value: '500600700' } })
    fireEvent.change(screen.getByLabelText('Kanał komunikacji'), { target: { value: 'sms' } })
    fireEvent.change(screen.getByLabelText('Notatka'), { target: { value: 'Wózek dziecięcy przy stoliku' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zaproponuj przydział' }))

    expect(await screen.findByText('Brak zestawu dla 6 osób.')).toBeInTheDocument()
    const transfer = screen.getByRole('button', { name: 'Przenieś do oczekujących' })
    expect(transfer).toHaveClass('min-h-11')
    fireEvent.click(transfer)

    expect(await screen.findByRole('heading', { name: `Lista oczekujących · ${TEST_DATE}` })).toBeInTheDocument()
    const waitlistDialog = screen.getByRole('dialog')
    expect(screen.getByText(/Przenieśliśmy wpisane dane/)).toBeInTheDocument()
    const waitlistName = screen.getByLabelText('Nazwisko / klient')
    expect(waitlistName).toHaveValue('Kowalska')
    expect(screen.getByLabelText('Preferowana godzina')).toHaveValue('18:00')
    expect(screen.getByLabelText('Liczba osób')).toHaveValue(6)
    expect(screen.getByLabelText('Telefon')).toHaveValue('500600700')
    expect(screen.getByLabelText('Kanał komunikacji')).toHaveValue('sms')
    expect(screen.getByLabelText('Notatka wewnętrzna')).toHaveValue('Wózek dziecięcy przy stoliku')
    await act(async () => {
      await new Promise((resolve) => window.requestAnimationFrame(resolve))
    })
    expect(waitlistDialog).toContainElement(document.activeElement)
    expect(waitlistName).toHaveFocus()
    expect(reservationTrigger).not.toHaveFocus()

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj do listy' }))
    await waitFor(() => expect(waitlistBody).toEqual(expect.objectContaining({
      data: TEST_DATE,
      godz_od: '18:00',
      liczba_osob: 6,
      nazwisko: 'Kowalska',
      telefon: '500600700',
      kanal_komunikacji: 'sms',
      notatka: 'Wózek dziecięcy przy stoliku',
    })))
  })

  it('nie proponuje waitlisty, gdy symulacja nie odpowiedziała', async () => {
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/reguly/symuluj' && method === 'POST') {
        return Promise.reject(new Error('Brak połączenia z serwerem.'))
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    fireEvent.change(screen.getByLabelText('Liczba osób'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zaproponuj przydział' }))

    expect(await screen.findByText('Brak połączenia z serwerem.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Przenieś do oczekujących' })).not.toBeInTheDocument()
  })

  it('walk-in z ręcznym stolikiem pokazuje blokadę i nie uruchamia automatu', async () => {
    let createBody
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === '/rezerwacje-stolik' && method === 'POST') {
        createBody = body
        return Promise.resolve({ ...RESERVATION, ...body, id: 40, status: 'potwierdzona' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })
    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))

    const mode = screen.getByRole('group', { name: 'Tryb tworzenia rezerwacji' })
    const walkIn = screen.getByRole('button', { name: 'Walk-in (gość na miejscu)' })
    expect(mode).toBeInTheDocument()
    expect(walkIn).toHaveClass('min-h-11')
    fireEvent.click(walkIn)
    const modeHelp = screen.getByText(/Gość jest już na miejscu/)
    expect(mode).toHaveAttribute('aria-describedby', modeHelp.id)
    expect(modeHelp).toHaveAttribute('aria-live', 'polite')
    fireEvent.change(screen.getByLabelText('Stolik'), { target: { value: String(TABLE.id) } })

    expect(walkIn).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { name: 'Przypisano ręcznie' })).toBeInTheDocument()
    expect(screen.getByText('Sala · T3')).toBeInTheDocument()
    expect(screen.getByText('Automat nie zmieni tego przydziału.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zaproponuj przydział' })).not.toBeInTheDocument()
    expect(apiMock.mock.calls.some(([path]) => path === '/rezerwacje/reguly/symuluj')).toBe(false)
    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Gość przy barze' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))
    await waitFor(() => expect(createBody).toEqual(expect.objectContaining({
      kanal: 'walk_in',
      stolik_id: TABLE.id,
      nazwisko: 'Gość przy barze',
    })))
    expect(createBody).not.toHaveProperty('auto_przydziel')
  })

  it('tworzy walk-in bez stolika i pozostawia automatyczny przydział backendowi', async () => {
    let createBody
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === '/rezerwacje-stolik' && method === 'POST') {
        createBody = body
        return Promise.resolve({ ...RESERVATION, ...body, id: 41, status: 'potwierdzona' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    fireEvent.click(screen.getByRole('button', { name: 'Walk-in (gość na miejscu)' }))
    fireEvent.change(screen.getByLabelText('Liczba osób'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Gość z ulicy' } })

    expect(screen.getByText(/Gość jest już na miejscu/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => expect(createBody).toEqual(expect.objectContaining({
      kanal: 'walk_in',
      auto_przydziel: true,
      stolik_id: null,
      liczba_osob: 3,
      nazwisko: 'Gość z ulicy',
    })))
    expect(apiMock.mock.calls.some(([path]) => path === '/rezerwacje/reguly/symuluj')).toBe(false)
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
    const createBodies = []
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
        createBodies.push(body)
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
    expect(createBodies).toHaveLength(2)
    expect(createBodies[0]).toEqual(expect.objectContaining({
      kanal: 'reczna',
      auto_przydziel: true,
      stolik_id: null,
    }))
    expect(createBodies[1]).toEqual(createBodies[0])
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
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) {
        listLoads += 1
        return Promise.resolve({ rezerwacje: [] })
      }
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/zrealizuj` && method === 'POST') {
        expect(body).toEqual({ stolik_id: TABLE.id, tryb: 'walk_in' })
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

  it('pokazuje uwagę komunikacyjną przy wpisie listy oczekujących bez wielu live regionów', async () => {
    mockInitial({
      waitlist: [{
        ...WAITLIST_ENTRY,
        communication_summary: {
          state: 'uncertain',
          channel: 'sms',
          attention_required: true,
          attention_count: 2,
        },
      }],
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Oczekujący (1)' }))

    const badge = screen.getByLabelText('Sprawdź wynik, SMS, 2 wiadomości wymagają uwagi')
    expect(badge).toHaveTextContent('2')
    expect(badge).not.toHaveAttribute('role', 'status')
  })

  it('otwiera historię wpisu bez niezależnego wysyłania komunikatu „stolik gotowy”', async () => {
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      if (path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/komunikacja` && method === 'GET') {
        expect(options.signal).toBeInstanceOf(AbortSignal)
        return Promise.resolve({
          summary: { state: 'queued', channel: 'sms', attention_count: 0 },
          messages: [{
            id: 301,
            event: 'table_ready',
            event_label: 'Oferta stolików',
            channel: 'sms',
            recipient: '***333',
            state: 'queued',
            attempt_count: 0,
            max_attempts: 5,
          }],
        })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Oczekujący (1)' }))
    const communication = screen.getByRole('button', { name: 'Komunikacja' })
    expect(communication).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(communication)

    expect(screen.getByRole('button', { name: 'Zwiń komunikację' })).toHaveAttribute('aria-expanded', 'true')
    expect(await screen.findByText('Oferta stolików')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Powiadom: stolik gotowy' })).not.toBeInTheDocument()
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/powiadom'))).toBe(false)
  })

  it('dla wycofanej oferty pozwala uzgodnić niepewny wynik bez kolejki i nieaktualnego retry', async () => {
    authState.isAdmin = false
    authState.permissions = ['rezerwacje.host', 'rezerwacje.dane_kontaktowe']
    const uncertainMessage = {
      id: 302,
      event: 'table_ready',
      event_label: 'Oferta stolików',
      channel: 'sms',
      recipient: '***333',
      state: 'uncertain',
      attention_required: true,
      attempt_count: 1,
      max_attempts: 5,
      retry_allowed: false,
    }
    let reconciled = false
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      if (path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/komunikacja` && method === 'GET') {
        const message = reconciled
          ? { ...uncertainMessage, state: 'failed', attention_required: false }
          : uncertainMessage
        return Promise.resolve({
          waitlist_id: WAITLIST_ENTRY.id,
          summary: { state: message.state, event: 'table_ready', channel: 'sms', attention_required: !reconciled, attention_count: reconciled ? 0 : 1 },
          messages: [message],
        })
      }
      if (path === `/rezerwacje/komunikacja/${uncertainMessage.id}/reconcile` && method === 'POST') {
        expect(body).toEqual({ wynik: 'failed', notatka: 'Brak wiadomości w panelu operatora SMS.' })
        reconciled = true
        return Promise.resolve({ ...uncertainMessage, state: 'failed' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Oczekujący (1)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Komunikacja' }))

    expect(await screen.findByText(/ponowienie może wysłać duplikat/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Oznacz jako wysłaną' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Oznacz jako niewysłaną' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Ponów mimo ryzyka' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Powiadom: stolik gotowy' })).not.toBeInTheDocument()
    expect(screen.getByText(/Możesz go oznaczyć, ale nie ponawiać wysyłki/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Wynik sprawdzenia'), {
      target: { value: 'Brak wiadomości w panelu operatora SMS.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Oznacz jako niewysłaną' }))

    expect(await screen.findByText('Wiadomość oznaczono jako niewysłaną.')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      `/rezerwacje/komunikacja/${uncertainMessage.id}/reconcile`,
      'POST',
      { wynik: 'failed', notatka: 'Brak wiadomości w panelu operatora SMS.' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('pozwala operatorowi z kontaktem wysłać komunikat wyłącznie dla aktywnej oferty', async () => {
    const offeredEntry = {
      ...WAITLIST_ENTRY,
      status: 'zaoferowano',
      offer_version: 1,
      hold_stolik_id: TABLE.id,
      hold_stoliki_dodatkowe: [],
      hold_godz_od: '19:00',
      hold_godz_do: '20:30',
      hold_do: '2030-03-01T18:10:00.000Z',
    }
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [offeredEntry] })
      if (path === `/lista-oczekujacych/${offeredEntry.id}/komunikacja` && method === 'GET') {
        return Promise.resolve({ summary: null, messages: [] })
      }
      if (path === `/lista-oczekujacych/${offeredEntry.id}/powiadom` && method === 'POST') {
        expect(options.signal).toBeInstanceOf(AbortSignal)
        expect(options.headers['Idempotency-Key']).toBe('manual-reservation-test-key')
        return Promise.resolve({ queued: true, wpis: offeredEntry, messages: [] })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Oczekujący (1)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Komunikacja' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Powiadom: stolik gotowy' }))

    expect(await screen.findByText('Dodano powiadomienie „stolik gotowy” do kolejki.')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      `/lista-oczekujacych/${offeredEntry.id}/powiadom`,
      'POST',
      null,
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        headers: { 'Idempotency-Key': 'manual-reservation-test-key' },
      }),
    )
  })

  it('przy przekroczeniu z listy oczekujących wymaga powodu i wysyła audytowalne nadpisanie', async () => {
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
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/zrealizuj` && method === 'POST') {
        attempts += 1
        if (attempts === 1) {
          const error = new Error('Limit osób w wybranym oknie został przekroczony.')
          error.availability = {
            decision: 'override_required',
            violations: [{
              code: 'PACING_COVERS_LIMIT',
              limit: 20,
              observed: 19,
              projected: 21,
              message: 'Limit nowych osób w ciągu 30 minut',
              overrideable_by_operator: true,
            }],
          }
          return Promise.reject(error)
        }
        return Promise.resolve({
          wpis: { ...WAITLIST_ENTRY, status: 'zrealizowany', termin_id: 32 },
          rezerwacja: { ...RESERVATION, ...body, id: 32, nazwisko: WAITLIST_ENTRY.nazwisko },
        })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Oczekujący (1)' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Stolik dla Kowalska' }), { target: { value: String(TABLE.id) } })
    fireEvent.click(screen.getByRole('button', { name: 'Posadź' }))

    expect(await screen.findByText('Limit nowych osób w ciągu 30 minut')).toBeInTheDocument()
    const overrideButton = screen.getByRole('button', { name: 'Posadź mimo limitu' })
    expect(overrideButton).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'walk_in' } })
    fireEvent.click(overrideButton)

    await waitFor(() => expect(attempts).toBe(2))
    const overrideBody = apiMock.mock.calls.filter(
      ([path, method]) => path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/zrealizuj` && method === 'POST',
    )[1][2]
    expect(overrideBody).toEqual({
      stolik_id: TABLE.id,
      tryb: 'walk_in',
      przekrocz_limity: true,
      nadpisanie_limitow: {
        powod: 'walk_in',
        notatka: null,
        potwierdzone: true,
      },
    })
  })

  it('na stanowisku posadza z listy oczekujących dopiero po reautoryzacji i przekazuje grant w nagłówku', async () => {
    authState.isAdmin = false
    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.nadpisuj_limity',
    ]
    authState.workstationSession = { active: true, station: { id: 'desk-1' }, user: { id: 12 } }
    reauthorizeWorkstationMock.mockResolvedValue({ grant: 'wreauth-waitlist' })
    let attempts = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [WAITLIST_ENTRY] })
      if (path === '/rezerwacje/config') return Promise.resolve({ sale: [] })
      if (path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/zrealizuj` && method === 'POST') {
        attempts += 1
        if (attempts === 1) {
          const error = new Error('Limit osób w wybranym oknie został przekroczony.')
          error.availability = { decision: 'override_required', violations: [] }
          return Promise.reject(error)
        }
        return Promise.resolve({
          wpis: { ...WAITLIST_ENTRY, status: 'zrealizowany', termin_id: 33 },
          rezerwacja: { ...RESERVATION, ...body, id: 33, nazwisko: WAITLIST_ENTRY.nazwisko },
        })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Oczekujący (1)' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Stolik dla Kowalska' }), { target: { value: String(TABLE.id) } })
    fireEvent.click(screen.getByRole('button', { name: 'Posadź' }))
    await screen.findByRole('button', { name: 'Potwierdź PIN-em i posadź' })
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'walk_in' } })
    fireEvent.change(screen.getByLabelText('Twój 6-cyfrowy PIN'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź PIN-em i posadź' }))

    await waitFor(() => expect(attempts).toBe(2))
    const retryCall = apiMock.mock.calls.filter(
      ([path, method]) => path === `/lista-oczekujacych/${WAITLIST_ENTRY.id}/zrealizuj` && method === 'POST',
    )[1]
    expect(retryCall[2]).not.toHaveProperty('pin')
    expect(retryCall[3].headers).toEqual({ 'X-Lokalo-Workstation-Reauth': 'wreauth-waitlist' })
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
          error.availability = {
            decision: 'override_required',
            can_override: true,
            violations: [{
              rule: 'pacing_reservations',
              code: 'PACING_RESERVATION_LIMIT',
              limit: 4,
              observed: 4,
              projected: 5,
              message: 'Limit nowych rezerwacji w ciągu 30 minut',
            }],
          }
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
    expect(screen.getByRole('button', { name: 'Zapisz mimo limitu' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'operational_decision' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz mimo limitu' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const overrideBody = apiMock.mock.calls.filter(
      ([path, method]) => path === '/rezerwacje-stolik' && method === 'POST',
    )[1][2]
    expect(overrideBody.przekrocz_limity).toBe(true)
    expect(overrideBody.nadpisanie_limitow).toEqual({
      powod: 'operational_decision',
      notatka: null,
      potwierdzone: true,
    })
  })

  it('na stanowisku reautoryzuje override własnym PIN-em i używa grantu tylko w nagłówku retry', async () => {
    authState.isAdmin = false
    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.nadpisuj_limity',
    ]
    authState.workstationSession = { active: true, station: { id: 'desk-1' }, user: { id: 12 } }
    reauthorizeWorkstationMock.mockResolvedValue({
      grant: 'wreauth-single-use',
      scope: 'reservation_override',
    })
    let attempts = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje-stolik' && method === 'POST') {
        attempts += 1
        if (attempts === 1) {
          const error = new Error('Osiągnięto limit nowych rezerwacji.')
          error.availability = {
            decision: 'override_required',
            can_override: true,
            violations: [{
              code: 'PACING_RESERVATION_LIMIT',
              message: 'Limit nowych rezerwacji w ciągu 30 minut',
            }],
          }
          return Promise.reject(error)
        }
        return Promise.resolve({ ...RESERVATION, ...body, id: 56, status: 'potwierdzona' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'PIN Test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    const overrideButton = await screen.findByRole('button', { name: 'Potwierdź PIN-em i zapisz' })
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'operational_decision' } })
    fireEvent.change(screen.getByLabelText('Twój 6-cyfrowy PIN'), { target: { value: '123456' } })
    fireEvent.click(overrideButton)

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(reauthorizeWorkstationMock).toHaveBeenCalledWith({
      pin: '123456',
      scope: 'reservation_override',
      signal: expect.any(AbortSignal),
    })
    const retryCall = apiMock.mock.calls.filter(
      ([path, method]) => path === '/rezerwacje-stolik' && method === 'POST',
    )[1]
    expect(retryCall[2]).not.toHaveProperty('pin')
    expect(retryCall[2]).not.toHaveProperty('grant')
    expect(retryCall[3].headers).toEqual(expect.objectContaining({
      'Idempotency-Key': 'manual-reservation-test-key',
      'X-Lokalo-Workstation-Reauth': 'wreauth-single-use',
    }))
  })

  it('przy edycji na stanowisku przekazuje jednorazowy grant poza treścią rezerwacji', async () => {
    authState.isAdmin = false
    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.nadpisuj_limity',
    ]
    authState.workstationSession = { active: true, station: { id: 'desk-1' }, user: { id: 12 } }
    reauthorizeWorkstationMock.mockResolvedValue({ grant: 'wreauth-edit' })
    let attempts = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [RESERVATION] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === `/rezerwacje-stolik/${RESERVATION.id}` && method === 'PUT') {
        attempts += 1
        if (attempts === 1) {
          const error = new Error('Zmiana przekracza limit osób.')
          error.availability = { decision: 'override_required', can_override: true, violations: [] }
          return Promise.reject(error)
        }
        return Promise.resolve({ ...RESERVATION, ...body })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj rezerwację: Nowak' }))
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Nowak – większa grupa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))
    await screen.findByRole('button', { name: 'Potwierdź PIN-em i zapisz' })
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'large_group_confirmed' } })
    fireEvent.change(screen.getByLabelText('Twój 6-cyfrowy PIN'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź PIN-em i zapisz' }))

    await waitFor(() => expect(attempts).toBe(2))
    const retryCall = apiMock.mock.calls.filter(
      ([path, method]) => path === `/rezerwacje-stolik/${RESERVATION.id}` && method === 'PUT',
    )[1]
    expect(retryCall[2]).not.toHaveProperty('pin')
    expect(retryCall[3].headers).toEqual({ 'X-Lokalo-Workstation-Reauth': 'wreauth-edit' })
  })

  it('po błędnym PIN-ie i 429 zachowuje formularz oraz powód override', async () => {
    authState.isAdmin = false
    authState.permissions = [
      'rezerwacje.operacje',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.nadpisuj_limity',
    ]
    authState.workstationSession = { active: true, station: { id: 'desk-1' }, user: { id: 12 } }
    const pinError = new Error('Nieprawidłowy PIN.')
    pinError.status = 429
    pinError.code = 'WORKSTATION_REAUTH_FAILED'
    pinError.retryAfter = 30
    reauthorizeWorkstationMock.mockRejectedValue(pinError)
    let attempts = 0
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki') return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/rezerwacje-stolik' && method === 'POST') {
        attempts += 1
        const error = new Error('Osiągnięto limit nowych rezerwacji.')
        error.availability = { decision: 'override_required', can_override: true, violations: [] }
        return Promise.reject(error)
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj rezerwację' }))
    fireEvent.change(screen.getByLabelText('Nazwisko / klient'), { target: { value: 'Nie zgub mnie' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))
    await screen.findByRole('button', { name: 'Potwierdź PIN-em i zapisz' })
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'guest_request' } })
    fireEvent.change(screen.getByLabelText('Twój 6-cyfrowy PIN'), { target: { value: '654321' } })
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź PIN-em i zapisz' }))

    expect((await screen.findByRole('alert')).parentElement).toHaveTextContent('Nieprawidłowy PIN. Spróbuj ponownie za 30 s.')
    expect(screen.getByRole('dialog', { name: 'Nowa rezerwacja' })).toBeInTheDocument()
    expect(screen.getByLabelText('Nazwisko / klient')).toHaveValue('Nie zgub mnie')
    expect(screen.getByLabelText('Powód przekroczenia')).toHaveValue('guest_request')
    expect(screen.getByLabelText('Twój 6-cyfrowy PIN')).toHaveValue('')
    expect(attempts).toBe(1)
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
    expect(screen.queryByRole('group', { name: 'Tryb tworzenia rezerwacji' })).not.toBeInTheDocument()
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
    expect(updateBody).not.toHaveProperty('kanal')
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
