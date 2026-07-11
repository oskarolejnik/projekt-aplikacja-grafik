// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, confirmMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({
  api: apiMock,
  nowyKluczIdempotencji: () => 'manual-reservation-test-key',
}))
vi.mock('../ui/Toast', () => ({
  useToast: () => ({ confirm: confirmMock, toast: vi.fn() }),
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

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
    if (path === '/lokal/config') return Promise.resolve({ sale: ['Sala', 'Taras'] })
    return Promise.reject(new Error(`Nieoczekiwany endpoint: GET ${path}`))
  })
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  confirmMock.mockResolvedValue(true)
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
      if (path === '/lokal/config') return Promise.resolve({ sale: [] })
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
      if (path === '/lokal/config') return Promise.resolve({ sale: [] })
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
      if (path === '/lokal/config') return Promise.resolve({ sale: [] })
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

  it('zachowuje formularz stolika po błędzie i dodaje go lokalnie po retry', async () => {
    let attempts = 0
    let tableLoads = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki' && !method) {
        tableLoads += 1
        return Promise.resolve({ stoliki: [TABLE] })
      }
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/lokal/config') return Promise.resolve({ sale: ['Sala'] })
      if (path === '/stoliki' && method === 'POST') {
        attempts += 1
        return attempts === 1
          ? Promise.reject(new Error('Serwer niedostępny.'))
          : Promise.resolve({ ...TABLE, ...body, id: 8 })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Stoliki (1)' }))
    const name = screen.getByLabelText('Nazwa')
    fireEvent.change(name, { target: { value: 'T8' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj stolik' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Serwer niedostępny.')
    expect(name).toHaveValue('T8')
    fireEvent.click(screen.getByRole('button', { name: 'Ponów dodanie' }))

    expect(await screen.findByText('T8')).toBeInTheDocument()
    expect(screen.getByText('Dodano stolik: T8.')).toBeInTheDocument()
    expect(attempts).toBe(2)
    expect(tableLoads).toBe(1)
  })

  it('wyłącza nieużywany stolik bez usuwania go z konfiguracji', async () => {
    apiMock.mockImplementation((path, method, body) => {
      if (path.startsWith('/rezerwacje-stolik?')) return Promise.resolve({ rezerwacje: [] })
      if (path === '/stoliki' && !method) return Promise.resolve({ stoliki: [TABLE] })
      if (path.startsWith('/lista-oczekujacych?')) return Promise.resolve({ lista: [] })
      if (path === '/lokal/config') return Promise.resolve({ sale: ['Sala'] })
      if (path === `/stoliki/${TABLE.id}` && method === 'PUT') {
        return Promise.resolve({ ...TABLE, ...body })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<RezerwacjeStolik />)
    fireEvent.click(await screen.findByRole('button', { name: 'Stoliki (1)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Wyłącz' }))

    expect(await screen.findByText('Nieaktywny')).toBeInTheDocument()
    expect(screen.getByText('Stolik wyłączono z nowych rezerwacji.')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      `/stoliki/${TABLE.id}`,
      'PUT',
      expect.objectContaining({ aktywny: false, nazwa: TABLE.nazwa, pojemnosc: TABLE.pojemnosc }),
    )
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
      if (path === '/lokal/config') return Promise.resolve({ sale: [] })
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
})
