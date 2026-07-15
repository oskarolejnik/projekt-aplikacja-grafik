// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, confirmMock, privacyState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  privacyState: { callback: null },
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../lib/icons', () => ({ Icon: ({ name }) => <span aria-hidden="true">{name}</span> }))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ confirm: confirmMock }) }))
vi.mock('../../lib/reservationPrivacy', () => ({
  subscribeReservationPrivacyPurge: (callback) => {
    privacyState.callback = callback
    return () => { if (privacyState.callback === callback) privacyState.callback = null }
  },
}))

import ReservationAvailability from './ReservationAvailability'

const RULES = {
  polityka: {
    okno_wyprzedzenia_dni: 90,
    cutoff_min: 60,
    bufor_min: 15,
    min_grupa_online: 1,
    max_grupa_online: 18,
  },
  serwisy: [{
    id: 11,
    dzien_tygodnia: 5,
    nazwa: 'Kolacja',
    godz_od: '17:00',
    godz_do: '23:00',
    krok_slotu_min: 15,
    domyslny_turn_time_min: 120,
    pacing_okno_min: 30,
    pacing_max_rez: 4,
    pacing_max_osob: 24,
    duza_grupa_od: 10,
    duza_grupa_tryb: 'do_zatwierdzenia',
    aktywny: true,
  }],
  nadpisania: [],
  wyjatki: [{ id: 3, data: '2026-12-24', typ: 'blackout', nazwa: 'Wigilia' }],
  sale: [{
    id: 2,
    nazwa: 'Ogród',
    aktywna: true,
    online_aktywna: true,
    wewnetrzna_aktywna: true,
    limit_jednoczesnych_rez: null,
    limit_jednoczesnych_osob: 32,
    domyslny_bufor_min: null,
  }],
}

beforeEach(() => {
  apiMock.mockReset()
  confirmMock.mockReset()
  confirmMock.mockResolvedValue(true)
  privacyState.callback = null
  apiMock.mockImplementation((path, method) => {
    if (path === '/rezerwacje/reguly' && method === 'GET') return Promise.resolve(RULES)
    if (path === '/rezerwacje/reguly/symuluj' && method === 'POST') return Promise.resolve({
      decision: 'override_required',
      available: false,
      service: { id: 11, name: 'Kolacja' },
      visit_end: '20:30',
      resource_allocation: 'recommended',
      allocation: {
        state: 'preview',
        visibility: 'exact',
        room: { id: 2, name: 'Ogród' },
        tables: [
          { id: 21, name: 'O1', capacity: 6 },
          { id: 22, name: 'O2', capacity: 6 },
        ],
        capacity: 12,
        visit_end: '20:30',
        reasons: [
          { code: 'CAPACITY_FIT', message: '12 miejsc dla 12 osób' },
          { code: 'TABLES_ADJACENT', message: 'Stoły sąsiadują' },
        ],
      },
      alternatives: [{
        id: 'later',
        kind: 'time',
        date: '2026-08-22',
        time: '18:30',
        allocation: {
          room: { id: 2, name: 'Ogród' },
          tables: [{ id: 23, name: 'O3', capacity: 12 }],
        },
      }],
      checks: [],
      violations: [{
        rule: 'pacing_covers',
        code: 'PACING_COVERS_LIMIT',
        limit: 24,
        observed: 18,
        projected: 30,
        message: 'Limit nowych osób w ciągu 30 minut',
        scope: { type: 'room_channel', sala_id: 2, kanal: 'wewnetrzna' },
      }],
    })
    if (method === 'PUT' || method === 'POST' || method === 'DELETE') return Promise.resolve({})
    return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
  })
})

afterEach(() => cleanup())

describe('ReservationAvailability', () => {
  it('pokazuje prosty tryb i pełną symulację dostępności z przydziałem oraz alternatywami', async () => {
    render(<ReservationAvailability />)

    expect(await screen.findByRole('heading', { name: 'Najważniejsze zasady' })).toBeInTheDocument()
    expect(screen.getByText(/Kolacja/)).toBeInTheDocument()
    expect(screen.getByText(/Wigilia/)).toBeInTheDocument()
    expect(screen.getByText('Zobacz decyzję, proponowany przydział i bezpieczne alternatywy dla konkretnej rezerwacji.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Dzień'), { target: { value: '2026-08-22' } })
    fireEvent.change(screen.getByLabelText('Godzina'), { target: { value: '18:00' } })
    fireEvent.change(screen.getByLabelText('Liczba osób'), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText('Sala'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź dostępność' }))

    expect(await screen.findByText('Wymaga decyzji obsługi — przekroczona 1 reguła')).toBeInTheDocument()
    expect(screen.getByText('Ogród · O1 + O2')).toBeInTheDocument()
    expect(screen.getByText('12 miejsc · do 20:30')).toBeInTheDocument()
    expect(screen.getByText('12 miejsc dla 12 osób')).toBeInTheDocument()
    expect(screen.getByText('Podgląd nie blokuje stołów; przydział potwierdzi się przy zapisie.')).toBeInTheDocument()
    expect(screen.getByText('Limit nowych osób w ciągu 30 minut')).toBeInTheDocument()
    expect(screen.getByText('Szczegóły decyzji · 1 reguła').closest('details')).toHaveAttribute('open')
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż 1 alternatywę' }))
    expect(screen.getByText('2026-08-22 · 18:30 · Ogród · O3')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/rezerwacje/reguly/symuluj', 'POST', {
      data: '2026-08-22',
      godz_od: '18:00',
      liczba_osob: 12,
      kanal: 'wewnetrzna',
      sala_id: 2,
    }, expect.objectContaining({ signal: expect.any(AbortSignal) }))

    fireEvent.change(screen.getByLabelText('Liczba osób'), { target: { value: '13' } })
    expect(screen.queryByText('Wymaga decyzji obsługi — przekroczona 1 reguła')).not.toBeInTheDocument()
  })

  it('zapisuje lokalny szkic zasad i dopiero potem odświeża konfigurację', async () => {
    render(<ReservationAvailability />)
    const advance = await screen.findByLabelText(/Rezerwacje z wyprzedzeniem/)
    fireEvent.change(advance, { target: { value: '120' } })
    expect(screen.getByText('Niezapisane zmiany')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Zapisz zasady' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje/reguly/polityka',
      'PUT',
      {
        okno_wyprzedzenia_dni: 120,
        cutoff_min: 60,
        bufor_min: 15,
        min_grupa_online: 1,
        max_grupa_online: 18,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    await waitFor(() => expect(apiMock.mock.calls.filter(([path, method]) => path === '/rezerwacje/reguly' && method === 'GET')).toHaveLength(2))
  })

  it('nie wysyła sprzecznego zakresu grup i wyjaśnia błąd przy formularzu', async () => {
    render(<ReservationAvailability />)
    fireEvent.change(await screen.findByLabelText(/Najmniejsza grupa online/), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText(/Największa grupa online/), { target: { value: '8' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz zasady' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Największa grupa online nie może być mniejsza od najmniejszej.')
    expect(apiMock.mock.calls.some(([path, method]) => path === '/rezerwacje/reguly/polityka' && method === 'PUT')).toBe(false)
  })

  it('zapis innej sekcji zachowuje niezapisany szkic zasad ogólnych', async () => {
    render(<ReservationAvailability />)
    const advance = await screen.findByLabelText(/Rezerwacje z wyprzedzeniem/)
    fireEvent.change(advance, { target: { value: '120' } })

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj wyjątek' }))
    fireEvent.change(screen.getByLabelText('Nazwa / powód'), { target: { value: 'Przegląd instalacji' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz wyjątek' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/wyjatki-kalendarza',
      'POST',
      expect.objectContaining({ nazwa: 'Przegląd instalacji' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    await waitFor(() => expect(advance).toHaveValue(120))
    expect(screen.getByText('Niezapisane zmiany')).toBeInTheDocument()
  })

  it('kreator jednego serwisu zapisuje wybrane dni jako spójne wpisy API', async () => {
    render(<ReservationAvailability />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj serwis' }))
    expect(screen.getByRole('heading', { name: 'Nowy serwis' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Nazwa serwisu'), { target: { value: 'Weekend' } })
    fireEvent.click(screen.getByText('Dokładniejsze limity tego serwisu'))
    fireEvent.change(screen.getByLabelText(/^Duża grupa od/), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText(/^Obsługa dużych grup/), { target: { value: 'telefon' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz serwis' }))

    await waitFor(() => expect(apiMock.mock.calls.filter(([path, method]) => path === '/godziny-otwarcia' && method === 'POST')).toHaveLength(2))
    const payloads = apiMock.mock.calls
      .filter(([path, method]) => path === '/godziny-otwarcia' && method === 'POST')
      .map(([, , body]) => body)
    expect(payloads.map((body) => body.dzien_tygodnia)).toEqual([4, 5])
    expect(payloads.every((body) => (
      body.nazwa === 'Weekend'
      && body.krok_slotu_min === 15
      && body.duza_grupa_od === 12
      && body.duza_grupa_tryb === 'telefon'
    ))).toBe(true)
  })

  it('zapisuje dostępność i limity konkretnej sali bez odsłaniania ich w prostym widoku', async () => {
    render(<ReservationAvailability />)
    await screen.findByRole('heading', { name: 'Najważniejsze zasady' })

    expect(screen.queryByRole('heading', { name: 'Dostępność sal' })).not.toBeVisible()
    fireEvent.click(screen.getByText('Ustawienia zaawansowane'))
    expect(screen.getByRole('heading', { name: 'Dostępność sal' })).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Dostosuj dostępność sali Ogród' }))
    fireEvent.click(screen.getByRole('switch', { name: 'Rezerwacje online w sali Ogród' }))
    fireEvent.change(screen.getByLabelText('Maks. rezerwacji w sali'), { target: { value: '6' } })
    fireEvent.change(screen.getByLabelText('Maks. osób w sali'), { target: { value: '28' } })
    fireEvent.change(screen.getByLabelText(/^Bufor sali/), { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz dostępność sali' }))

    expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('ostatnia aktywna sala dostępna online'),
      expect.objectContaining({ title: 'Rezerwacje online zostaną zatrzymane' }),
    )

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje/reguly/sale/2',
      'PUT',
      {
        online_aktywna: false,
        wewnetrzna_aktywna: true,
        limit_jednoczesnych_rez: 6,
        limit_jednoczesnych_osob: 28,
        domyslny_bufor_min: 20,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
  })

  it('udostępnia pełny typed override dopiero po rozwinięciu dodatkowych reguł', async () => {
    render(<ReservationAvailability />)
    await screen.findByRole('heading', { name: 'Najważniejsze zasady' })
    fireEvent.click(screen.getByText('Ustawienia zaawansowane'))
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj własny limit' }))

    const form = screen.getByRole('button', { name: 'Zapisz limit' }).closest('form')
    fireEvent.change(within(form).getByLabelText('Sala'), { target: { value: '2' } })
    fireEvent.change(within(form).getByLabelText('Kanał'), { target: { value: 'online' } })
    fireEvent.change(within(form).getByLabelText('Serwis'), { target: { value: '11' } })
    fireEvent.change(within(form).getByLabelText('Maks. nowych rezerwacji'), { target: { value: '3' } })
    fireEvent.click(within(form).getByText('Więcej reguł dla tego zakresu'))
    fireEvent.change(within(form).getByLabelText(/^Bufor między wizytami/), { target: { value: '15' } })
    fireEvent.change(within(form).getByLabelText('Rezerwacje z wyprzedzeniem'), { target: { value: '45' } })
    fireEvent.change(within(form).getByLabelText('Zamknij rezerwacje przed terminem'), { target: { value: '120' } })
    fireEvent.change(within(form).getByLabelText('Najmniejsza grupa'), { target: { value: '2' } })
    fireEvent.change(within(form).getByLabelText(/^Największa grupa/), { target: { value: '18' } })
    fireEvent.change(within(form).getByLabelText('Duża grupa od'), { target: { value: '10' } })
    fireEvent.change(within(form).getByLabelText(/^Obsługa dużych grup/), { target: { value: 'do_zatwierdzenia' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Zapisz limit' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/nadpisania-regul-rezerwacji',
      'POST',
      {
        serwis_id: 11,
        sala_id: 2,
        kanal: 'online',
        pacing_okno_min: null,
        pacing_max_rez: 3,
        pacing_max_osob: null,
        max_jednoczesnych_rez: null,
        max_jednoczesnych_osob: null,
        bufor_min: 15,
        okno_wyprzedzenia_dni: 45,
        cutoff_min: 120,
        min_grupa: 2,
        max_grupa: 18,
        duza_grupa_od: 10,
        duza_grupa_tryb: 'do_zatwierdzenia',
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
  })

  it('edytuje istniejący wyjątek bez tworzenia duplikatu dnia', async () => {
    render(<ReservationAvailability />)
    const exceptionName = await screen.findByText(/Wigilia/)
    const exceptionRow = exceptionName.closest('div').parentElement

    fireEvent.click(within(exceptionRow).getByRole('button', { name: 'Edytuj' }))
    fireEvent.change(screen.getByLabelText('Nazwa / powód'), { target: { value: 'Wigilia — lokal zamknięty' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz wyjątek' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/wyjatki-kalendarza/3',
      'PUT',
      expect.objectContaining({
        data: '2026-12-24',
        typ: 'blackout',
        nazwa: 'Wigilia — lokal zamknięty',
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(apiMock.mock.calls.some(([path, method]) => path === '/wyjatki-kalendarza' && method === 'POST')).toBe(false)
  })
})
