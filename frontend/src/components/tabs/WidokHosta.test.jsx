// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const {
  apiMock,
  authState,
  idempotencyKeyMock,
  privacyState,
  reauthorizeWorkstationMock,
  subscribePurgeMock,
} = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authState: {
    isAdmin: false,
    permissions: [],
    user: { id: 17, login: 'recepcja' },
    workstationSession: null,
  },
  idempotencyKeyMock: vi.fn((scope) => `${scope}-test-key`),
  privacyState: { callback: null },
  reauthorizeWorkstationMock: vi.fn(),
  subscribePurgeMock: vi.fn((callback) => {
    privacyState.callback = callback
    return () => {
      if (privacyState.callback === callback) privacyState.callback = null
    }
  }),
}))

vi.mock('../../lib/api', () => ({
  api: apiMock,
  getApiBase: () => '',
  nowyKluczIdempotencji: idempotencyKeyMock,
}))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: authState.user,
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

import WidokHosta, { offerSuccessMessage, patchSnapshotReservation, visitTiming } from './WidokHosta'

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

const waitlistEntry = {
  id: 51,
  data: DAY,
  godz_od: '19:00',
  liczba_osob: 6,
  nazwisko: 'Nowak',
  status: 'oczekuje',
  priorytet: 0,
  utworzono_at: '2030-03-01T16:45:00.000Z',
  zaoferowano_at: null,
  hold_stolik_id: null,
  hold_stoliki_dodatkowe: [],
  hold_godz_od: null,
  hold_godz_do: null,
  hold_do: null,
  communication_summary: null,
  offer_version: 0,
}

const waitlistQueue = {
  data: DAY,
  nadchodzace: [],
  na_sali: [],
  zakonczone: [],
  waitlista: [waitlistEntry],
  podsumowanie: { nadchodzace: 0, na_sali: 0, coverow_na_sali: 0, zakonczone: 0, waitlista: 1 },
}

const waitlistFloor = {
  ...floor,
  stoliki: floor.stoliki.map((table) => ({
    ...table,
    status: 'wolny',
    rezerwacje: [],
  })),
  podsumowanie: { bez_rezerwacji: 2, zarezerwowane: 0, wstrzymane: 0, nieaktywne: 0, zajete_live: 0 },
}

const waitlistTimeline = { ...timeline, zajetosci: [] }

const waitlistSnapshot = () => makeSnapshot({
  nextQueue: waitlistQueue,
  nextFloor: waitlistFloor,
  nextTimeline: waitlistTimeline,
})

const offeredWaitlistEntry = {
  ...waitlistEntry,
  status: 'zaoferowano',
  zaoferowano_at: '2030-03-01T16:56:00.000Z',
  hold_stolik_id: 3,
  hold_stoliki_dodatkowe: [4],
  hold_godz_od: '19:00',
  hold_godz_do: '20:30',
  hold_do: '2030-03-01T18:10:00.000Z',
  offer_version: 1,
  communication_summary: {
    state: 'queued',
    channel: 'sms',
    attention_required: false,
    attention_count: 0,
  },
}

const expiringWaitlistEntry = {
  ...offeredWaitlistEntry,
  hold_do: '2030-03-01T16:55:05.000Z',
}

const expiringWaitlistSnapshot = () => makeSnapshot({
  nextQueue: {
    ...waitlistQueue,
    waitlista: [expiringWaitlistEntry],
  },
  nextFloor: waitlistFloor,
  nextTimeline: {
    ...waitlistTimeline,
    zajetosci: [3, 4].map((tableId) => ({
      typ: 'oferta',
      waitlist_id: expiringWaitlistEntry.id,
      rezerwacja_id: null,
      stolik_id: tableId,
      godz_od: expiringWaitlistEntry.hold_godz_od,
      godz_do: expiringWaitlistEntry.hold_godz_do,
      hold_do: expiringWaitlistEntry.hold_do,
      nazwisko: expiringWaitlistEntry.nazwisko,
      liczba_osob: expiringWaitlistEntry.liczba_osob,
    })),
  },
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
    authState.workstationSession = null
    idempotencyKeyMock.mockImplementation((scope) => `${scope}-test-key`)
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
    expect(await screen.findAllByRole('button', { name: /T3, 4 miejsca, Nadchodząca, Kowalska/ })).toHaveLength(1)
    expect(screen.getByLabelText('T3: Kowalska · 18:00–20:00, 6 osób')).toBeInTheDocument()
    expect(apiMock.mock.calls.filter(([path]) => path.startsWith('/host/snapshot?'))).toHaveLength(1)
    expect(apiMock.mock.calls.some(([path]) => path === '/stoliki' || path.startsWith('/host/kolejka'))).toBe(false)
  })

  it('prowadzi ofertę dla pełnej konfiguracji stolików aż do gotowej rezerwacji', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    const acceptedReservation = {
      id: 61,
      data: DAY,
      godz_od: '19:00',
      godz_do: '20:30',
      stolik_id: 3,
      stoliki_dodatkowe: [4],
      nazwisko: 'Nowak',
      liczba_osob: 6,
      status: 'potwierdzona',
      faza_hosta: null,
      gosc: null,
    }
    let snapshotLoads = 0
    apiMock.mockImplementation((path, method, body, options) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotLoads += 1
        return snapshotLoads === 1 ? Promise.resolve(waitlistSnapshot()) : new Promise(() => {})
      }
      if (path === `/host/sugestia-stolika?data=${DAY}&godz_od=19%3A00&osoby=6&waitlist_id=${waitlistEntry.id}` && method === 'GET') {
        return Promise.resolve({
          godz_od: '19:00',
          godz_do: '20:30',
          selected: { table_ids: [3, 4] },
          candidates: [{ table_ids: [3, 4] }, { table_ids: [3] }],
        })
      }
      if (path === `/lista-oczekujacych/${waitlistEntry.id}/oferta` && method === 'POST') {
        expect(body).toEqual({
          stoliki: [3, 4],
          godz_od: '19:00',
          minuty: 10,
          expected_offer_version: 0,
        })
        expect(options.headers['Idempotency-Key']).toBe('waitlist-offer-test-key')
        return Promise.resolve({ wpis: offeredWaitlistEntry, messages: [], queued: true })
      }
      if (path === `/lista-oczekujacych/${waitlistEntry.id}/zaakceptuj` && method === 'POST') {
        expect(body).toEqual({ tryb: 'rezerwacja', offer_version: 1 })
        expect(options.headers['Idempotency-Key']).toBe('waitlist-accept-test-key')
        return Promise.resolve({
          wpis: { ...offeredWaitlistEntry, status: 'zaakceptowano', offer_version: 2 },
          rezerwacja: acceptedReservation,
        })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dobierz stolik' }))

    expect(await screen.findByRole('button', { name: /T3 \+ T4.*Wybrano/ })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij ofertę · 10 min' }))

    expect(await screen.findByText('Zaoferowano')).toBeInTheDocument()
    expect(screen.getByText('Oferta aktywna. Powiadomienie jest w kolejce. Stoliki są trzymane do 19:10.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /T3, 4 miejsca, Oferta waitlisty, Nowak/ })).toBeInTheDocument()
    expect(screen.getByLabelText(/T3: Oferta dla Nowak · 19:00–20:30, 6 osób, ważna do 19:10/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Gość przyjął' }))

    const seat = await screen.findByRole('button', { name: 'Posadź' })
    expect(screen.getByText('Gość przyjął ofertę. Rezerwacja jest gotowa do posadzenia.')).toBeInTheDocument()
    await waitFor(() => expect(seat).toHaveFocus())
    expect(screen.queryByText('Zaoferowano')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /T3, 4 miejsca, Nadchodząca, Nowak/ })).toBeInTheDocument()
  })

  it('recepcja po ostrzeżeniu potwierdza przekroczenie PIN-em i ponawia tę samą ofertę z nowym kluczem', async () => {
    authState.permissions = [
      'rezerwacje.host',
      'rezerwacje.dane_kontaktowe',
      'rezerwacje.nadpisuj_limity',
    ]
    authState.workstationSession = { active: true, stationId: 4, operatorId: 17 }
    reauthorizeWorkstationMock.mockResolvedValue({ grant: 'wreauth-host-offer' })
    idempotencyKeyMock
      .mockReturnValueOnce('waitlist-offer-initial-key')
      .mockReturnValueOnce('waitlist-offer-override-key')

    let offerAttempts = 0
    let snapshotLoads = 0
    apiMock.mockImplementation((path, method, body, options) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotLoads += 1
        return snapshotLoads === 1 ? Promise.resolve(waitlistSnapshot()) : new Promise(() => {})
      }
      if (path.startsWith('/host/sugestia-stolika?') && method === 'GET') {
        return Promise.resolve({
          godz_od: '19:00',
          godz_do: '20:30',
          selected: { table_ids: [3, 4] },
          candidates: [{ table_ids: [3, 4] }],
        })
      }
      if (path === `/lista-oczekujacych/${waitlistEntry.id}/oferta` && method === 'POST') {
        offerAttempts += 1
        if (offerAttempts === 1) {
          expect(body).toEqual({
            stoliki: [3, 4],
            godz_od: '19:00',
            minuty: 15,
            expected_offer_version: 0,
          })
          expect(options.headers).toEqual({ 'Idempotency-Key': 'waitlist-offer-initial-key' })
          const conflict = new Error('Limit osób w wybranym oknie został przekroczony.')
          conflict.status = 409
          conflict.code = 'PACING_COVERS_LIMIT'
          conflict.availability = {
            decision: 'override_required',
            can_override: true,
            violations: [{
              code: 'PACING_COVERS_LIMIT',
              message: 'Maksymalnie 20 osób w tym oknie.',
              limit: 20,
              observed: 18,
              projected: 24,
              overrideable_by_operator: true,
            }],
          }
          return Promise.reject(conflict)
        }
        expect(body).toEqual({
          stoliki: [3, 4],
          godz_od: '19:00',
          minuty: 15,
          expected_offer_version: 0,
          przekrocz_limity: true,
          nadpisanie_limitow: {
            powod: 'large_group_confirmed',
            notatka: null,
            potwierdzone: true,
          },
        })
        expect(body).not.toHaveProperty('pin')
        expect(options.headers).toEqual({
          'Idempotency-Key': 'waitlist-offer-override-key',
          'X-Lokalo-Workstation-Reauth': 'wreauth-host-offer',
        })
        return Promise.resolve({ wpis: offeredWaitlistEntry, messages: [], queued: true })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dobierz stolik' }))
    fireEvent.change(await screen.findByLabelText('Ważność oferty'), { target: { value: '15' } })
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij ofertę · 15 min' }))

    expect(await screen.findByText('Limit osób w wybranym oknie został przekroczony.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ta operacja przekroczy ustawiony limit' })).toBeInTheDocument()
    expect(screen.getByText('Maksymalnie 20 osób w tym oknie.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wyślij ofertę · 15 min' })).toBeDisabled()
    const overrideButton = screen.getByRole('button', { name: 'Potwierdź PIN-em i wyślij ofertę' })
    expect(overrideButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'large_group_confirmed' } })
    fireEvent.change(screen.getByLabelText('Twój 6-cyfrowy PIN'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź PIN-em i wyślij ofertę' }))

    await waitFor(() => expect(reauthorizeWorkstationMock).toHaveBeenCalledWith({
      pin: '123456',
      scope: 'reservation_override',
      signal: expect.any(AbortSignal),
    }))
    expect(await screen.findByText('Zaoferowano')).toBeInTheDocument()
    expect(offerAttempts).toBe(2)
  })

  it('po nieznanym wyniku blokuje duplikat i po odświeżeniu ponawia ofertę z tym samym kluczem', async () => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    let snapshotLoads = 0
    let offerAttempts = 0
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotLoads += 1
        return snapshotLoads <= 2 ? Promise.resolve(waitlistSnapshot()) : new Promise(() => {})
      }
      if (path.startsWith('/host/sugestia-stolika?') && method === 'GET') {
        return Promise.resolve({
          godz_od: '19:00',
          godz_do: '20:30',
          selected: { table_ids: [3, 4] },
          candidates: [{ table_ids: [3, 4] }],
        })
      }
      if (path === `/lista-oczekujacych/${waitlistEntry.id}/oferta` && method === 'POST') {
        offerAttempts += 1
        expect(options.headers['Idempotency-Key']).toBe('waitlist-offer-test-key')
        return offerAttempts === 1
          ? Promise.reject(new TypeError('Failed to fetch'))
          : Promise.resolve({ wpis: offeredWaitlistEntry, messages: [], queued: false })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dobierz stolik' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Wyślij ofertę · 10 min' }))

    expect(await screen.findByText('Połączenie zostało przerwane. Nie znamy wyniku — odśwież widok przed ponowieniem.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wyślij ofertę · 10 min' })).toBeDisabled()
    expect(offerAttempts).toBe(1)

    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Wyślij ofertę · 10 min' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij ofertę · 10 min' }))

    expect(await screen.findByText('Oferta aktywna do 19:10. Poinformuj gościa na miejscu.')).toBeInTheDocument()
    expect(offerAttempts).toBe(2)
  })

  it.each(['TABLE_CONFLICT', 'WAITLIST_OFFER_PLAN_CHANGED'])(
    'po konflikcie konfiguracji %s usuwa martwy draft i prowadzi do ponownego doboru',
    async (conflictCode) => {
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    let snapshotLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotLoads += 1
        return Promise.resolve(waitlistSnapshot())
      }
      if (path.startsWith('/host/sugestia-stolika?') && method === 'GET') {
        return Promise.resolve({
          godz_od: '19:00',
          godz_do: '20:30',
          selected: { table_ids: [3, 4] },
          candidates: [{ table_ids: [3, 4] }],
        })
      }
      if (path === `/lista-oczekujacych/${waitlistEntry.id}/oferta` && method === 'POST') {
        const conflict = new Error('Stoliki zostały właśnie zajęte.')
        conflict.status = 409
        conflict.code = conflictCode
        return Promise.reject(conflict)
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dobierz stolik' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Wyślij ofertę · 10 min' }))

    expect(await screen.findByText('Wybrana konfiguracja nie jest już dostępna. Dobierz stoliki ponownie.')).toBeInTheDocument()
    expect(screen.queryByText('Wybierz konfigurację')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dobierz stolik' })).toBeEnabled()
    await waitFor(() => expect(snapshotLoads).toBe(2))
    expect(screen.queryByText(/Zapisy są chwilowo wyłączone/)).not.toBeInTheDocument()
    },
  )

  it('HOST z kontaktem uzgadnia niepewną wysyłkę lokalnie i ponawia ofertę z zachowanym szkicem', async () => {
    authState.permissions = ['rezerwacje.host', 'rezerwacje.dane_kontaktowe']
    const uncertainMessage = {
      id: 401,
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
    let offerAttempts = 0
    let reconciled = false
    let snapshotLoads = 0
    apiMock.mockImplementation((path, method, body) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotLoads += 1
        return snapshotLoads <= 2 ? Promise.resolve(waitlistSnapshot()) : new Promise(() => {})
      }
      if (path.startsWith('/host/sugestia-stolika?') && method === 'GET') {
        return Promise.resolve({
          godz_od: '19:00',
          godz_do: '20:30',
          selected: { table_ids: [3, 4] },
          candidates: [{ table_ids: [3, 4] }],
        })
      }
      if (path === `/lista-oczekujacych/${waitlistEntry.id}/oferta` && method === 'POST') {
        offerAttempts += 1
        if (offerAttempts === 1) {
          const conflict = new Error('Poprzednie powiadomienie wymaga uzgodnienia.')
          conflict.status = 409
          conflict.code = 'WAITLIST_DELIVERY_RECONCILIATION_REQUIRED'
          return Promise.reject(conflict)
        }
        return Promise.resolve({ wpis: offeredWaitlistEntry, messages: [], queued: true })
      }
      if (path === `/lista-oczekujacych/${waitlistEntry.id}/komunikacja` && method === 'GET') {
        const message = reconciled
          ? { ...uncertainMessage, state: 'failed', attention_required: false }
          : uncertainMessage
        return Promise.resolve({
          waitlist_id: waitlistEntry.id,
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

    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Dobierz stolik' }))
    fireEvent.change(await screen.findByLabelText('Ważność oferty'), { target: { value: '15' } })
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij ofertę · 15 min' }))

    const message = await screen.findByText('Nie znamy wyniku poprzedniej wysyłki. Przed nową ofertą wybierz „Komunikacja” przy tym wpisie i uzgodnij poprzednią wysyłkę.')
    expect(message.parentElement).toHaveAttribute('role', 'status')
    expect(message.parentElement).toHaveClass('text-lemon')
    expect(screen.getByRole('button', { name: /T3 \+ T4.*Wybrano/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Ważność oferty')).toHaveValue('15')
    expect(screen.getByRole('button', { name: 'Wyślij ofertę · 15 min' })).toBeEnabled()

    const communication = screen.getByRole('button', { name: 'Komunikacja' })
    expect(communication).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(communication)

    expect(await screen.findByText(/ponowienie może wysłać duplikat/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Oznacz jako wysłaną' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Oznacz jako niewysłaną' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Ponów mimo ryzyka' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Powiadom: stolik gotowy' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Wynik sprawdzenia'), {
      target: { value: 'Brak wiadomości w panelu operatora SMS.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Oznacz jako niewysłaną' }))

    expect(await screen.findByText('Wiadomość oznaczono jako niewysłaną.')).toBeInTheDocument()
    expect(screen.getByLabelText('Ważność oferty')).toHaveValue('15')
    expect(screen.getByRole('button', { name: 'Wyślij ofertę · 15 min' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij ofertę · 15 min' }))

    expect(await screen.findByText('Zaoferowano')).toBeInTheDocument()
    expect(offerAttempts).toBe(2)
  })

  it('dla aktywnej oferty z wyłączonym kanałem zostawia historię i reconcile bez aktywnego Powiadom', async () => {
    authState.permissions = ['rezerwacje.host', 'rezerwacje.dane_kontaktowe']
    const uncertainMessage = {
      id: 402,
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
    const noChannelEntry = {
      ...offeredWaitlistEntry,
      kanal_komunikacji: 'brak',
      can_queue_communication: false,
      communication_summary: {
        state: 'uncertain',
        event: 'table_ready',
        channel: 'sms',
        attention_required: true,
        attention_count: 1,
      },
    }
    const snapshot = makeSnapshot({
      nextQueue: { ...waitlistQueue, waitlista: [noChannelEntry] },
      nextFloor: waitlistFloor,
      nextTimeline: waitlistTimeline,
    })
    let reconciled = false
    apiMock.mockImplementation((path, method, body) => {
      if (path === `/host/snapshot?data=${DAY}`) return Promise.resolve(snapshot)
      if (path === `/lista-oczekujacych/${noChannelEntry.id}/komunikacja` && method === 'GET') {
        const message = reconciled
          ? { ...uncertainMessage, state: 'sent', attention_required: false }
          : uncertainMessage
        return Promise.resolve({
          waitlist_id: noChannelEntry.id,
          summary: { state: message.state, event: 'table_ready', channel: 'sms', attention_required: !reconciled, attention_count: reconciled ? 0 : 1 },
          messages: [message],
        })
      }
      if (path === `/rezerwacje/komunikacja/${uncertainMessage.id}/reconcile` && method === 'POST') {
        expect(body).toEqual({ wynik: 'sent', notatka: 'Potwierdzone w panelu operatora SMS.' })
        reconciled = true
        return Promise.resolve({ ...uncertainMessage, state: 'sent' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta date={DAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Komunikacja' }))

    expect(await screen.findByText(/ponowienie może wysłać duplikat/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Oznacz jako wysłaną' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Oznacz jako niewysłaną' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Powiadom: stolik gotowy' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Wynik sprawdzenia'), {
      target: { value: 'Potwierdzone w panelu operatora SMS.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Oznacz jako wysłaną' }))

    expect(await screen.findByText('Wiadomość oznaczono jako wysłaną.')).toBeInTheDocument()
  })

  it('pokazuje terminalną komunikację poza aktywną waitlistą i usuwa ją po uzgodnieniu', async () => {
    authState.permissions = ['rezerwacje.host', 'rezerwacje.dane_kontaktowe']
    const terminalEntry = {
      id: 61,
      nazwisko: 'Zielińska',
      status: 'anulowano',
      communication_summary: {
        state: 'uncertain',
        event: 'table_ready',
        channel: 'sms',
        attention_required: true,
        attention_count: 1,
      },
    }
    const uncertainMessage = {
      id: 461,
      event: 'table_ready',
      event_label: 'Stolik gotowy',
      channel: 'sms',
      recipient: '***222',
      state: 'uncertain',
      attention_required: true,
      attempt_count: 1,
      max_attempts: 5,
      retry_allowed: false,
    }
    const terminalSnapshot = makeSnapshot({
      nextQueue: {
        ...waitlistQueue,
        waitlista: [],
        komunikacja_waitlist: [terminalEntry],
        podsumowanie: {
          nadchodzace: 0,
          na_sali: 0,
          coverow_na_sali: 0,
          zakonczone: 0,
          waitlista: 0,
        },
      },
      nextFloor: waitlistFloor,
      nextTimeline: waitlistTimeline,
    })
    let reconciled = false
    apiMock.mockImplementation((path, method, body) => {
      if (path === `/host/snapshot?data=${DAY}`) return Promise.resolve(terminalSnapshot)
      if (path === `/lista-oczekujacych/${terminalEntry.id}/komunikacja` && method === 'GET') {
        return Promise.resolve({
          waitlist_id: terminalEntry.id,
          summary: reconciled
            ? { ...terminalEntry.communication_summary, state: 'sent', attention_required: false, attention_count: 0 }
            : terminalEntry.communication_summary,
          messages: [reconciled
            ? { ...uncertainMessage, state: 'sent', attention_required: false }
            : uncertainMessage],
        })
      }
      if (path === `/rezerwacje/komunikacja/${uncertainMessage.id}/reconcile` && method === 'POST') {
        expect(body).toEqual({ wynik: 'sent', notatka: 'Potwierdzone u dostawcy SMS.' })
        reconciled = true
        return Promise.resolve({ ...uncertainMessage, state: 'sent' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<WidokHosta date={DAY} />)

    expect(await screen.findByRole('heading', { name: 'Komunikacja do wyjaśnienia' })).toBeInTheDocument()
    expect(screen.getByText('Zielińska')).toBeInTheDocument()
    expect(screen.getByText('Oczekiwanie anulowane')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dobierz stolik' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Gość przyjął' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Anuluj oczekiwanie' })).not.toBeInTheDocument()

    const inspectCommunication = screen.getByRole('button', { name: 'Sprawdź komunikację' })
    setOnline(false)
    act(() => window.dispatchEvent(new Event('offline')))
    expect(inspectCommunication).toBeDisabled()
    setOnline(true)
    act(() => window.dispatchEvent(new Event('online')))
    await waitFor(() => expect(inspectCommunication).toBeEnabled())

    fireEvent.click(inspectCommunication)
    expect(await screen.findByText(/ponowienie może wysłać duplikat/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Powiadom: stolik gotowy' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Wynik sprawdzenia'), {
      target: { value: 'Potwierdzone u dostawcy SMS.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Oznacz jako wysłaną' }))

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Komunikacja do wyjaśnienia' })).not.toBeInTheDocument()
      expect(screen.queryByText('Zielińska')).not.toBeInTheDocument()
    })
  })

  it('po deadline lokalnie zwalnia stoliki i timeline mimo spóźnionego snapshotu serwera', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2040-01-01T12:00:00.000Z'))
    authState.permissions = ['rezerwacje.dane_kontaktowe']
    let snapshotLoads = 0
    apiMock.mockImplementation((path) => {
      if (path === `/host/snapshot?data=${DAY}`) {
        snapshotLoads += 1
        return Promise.resolve(expiringWaitlistSnapshot())
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<WidokHosta date={DAY} />)
    await act(async () => {})
    expect(screen.getByText('Zaoferowano')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /T3, 4 miejsca, Oferta waitlisty, Nowak/ })).toBeInTheDocument()
    expect(screen.getByLabelText(/T3: Oferta dla Nowak · 19:00–20:30, 6 osób, ważna do 17:55/)).toBeInTheDocument()

    await act(async () => { await vi.advanceTimersByTimeAsync(6_000) })
    await act(async () => {})

    expect(screen.queryByText('Zaoferowano')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /T3, 4 miejsca, Bez aktywnej wizyty/ })).toBeInTheDocument()
    expect(screen.queryByLabelText(/T3: Oferta/)).not.toBeInTheDocument()
    expect(snapshotLoads).toBe(2)
  })

  it('po odtworzeniu cache offline przesuwa zegar serwera i nie pokazuje wygasłej blokady', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2040-01-01T12:00:00.000Z'))
    apiMock.mockImplementation((path) => {
      if (path === `/host/snapshot?data=${DAY}`) return Promise.resolve(expiringWaitlistSnapshot())
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    const first = render(<WidokHosta date={DAY} />)
    await act(async () => {})
    expect(screen.getByText('Zaoferowano')).toBeInTheDocument()
    first.unmount()

    await vi.advanceTimersByTimeAsync(6_000)
    apiMock.mockClear()
    setOnline(false)
    render(<WidokHosta date={DAY} />)
    await act(async () => {})

    expect(screen.queryByText('Zaoferowano')).not.toBeInTheDocument()
    expect(screen.getByText('Tylko podgląd')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /T3, 4 miejsca, Bez aktywnej wizyty/ })).toBeInTheDocument()
    expect(screen.queryByLabelText(/T3: Oferta/)).not.toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
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

  it('przy replayu rozróżnia dostarczoną wiadomość od obsługi na miejscu', () => {
    expect(offerSuccessMessage({
      queued: false,
      wpis: {
        hold_do: offeredWaitlistEntry.hold_do,
        communication_summary: { state: 'sent', attention_required: false },
      },
      messages: [],
    }, Date.parse(GENERATED_AT))).toBe(
      'Oferta aktywna. Powiadomienie zostało dostarczone. Stoliki są trzymane do 19:10.',
    )
  })
})
