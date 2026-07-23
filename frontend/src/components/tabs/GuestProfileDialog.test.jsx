// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'
import GuestProfileDialog from './GuestProfileDialog'

const { apiMock, authState, confirmMock, keyMock, privacyState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authState: {
    isAdmin: true,
    permissions: new Set(),
    can: (permission) => authState.permissions.has(permission),
  },
  confirmMock: vi.fn(),
  keyMock: vi.fn(),
  privacyState: { callback: null },
}))

vi.mock('../../lib/api', () => ({
  api: apiMock,
  nowyKluczIdempotencji: keyMock,
}))
vi.mock('../../context/AuthContext', () => ({ useAuth: () => authState }))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ confirm: confirmMock }) }))
vi.mock('../../lib/reservationPrivacy', () => ({
  subscribeReservationPrivacyPurge: (callback) => {
    privacyState.callback = callback
    return () => { if (privacyState.callback === callback) privacyState.callback = null }
  },
}))

const response = ({
  reservationId = 42,
  name = 'Anna Kowalska',
  note = 'Lubi spokojny stolik',
  canEdit = true,
  canViewSensitive = true,
  canViewNotes = true,
  confident = true,
  history = null,
  consent = null,
} = {}) => ({
  reservation_id: reservationId,
  profil_ref: reservationId,
  nazwisko: name,
  identity: { source: confident ? 'telefon' : 'reservation', confident },
  profil: {
    nazwisko: name,
    tagi: canViewSensitive ? ['stały', 'okno'] : [],
    vip: true,
    alergie: canViewSensitive ? 'orzechy' : null,
    dieta: canViewSensitive ? 'wegetariańska' : null,
    preferowana_strefa: 'ogród',
    notatka: canViewNotes ? note : null,
    okazja_typ: 'urodziny',
    okazja_data: '05-12',
    marketing_zgoda: false,
  },
  statystyki: { wizyt: 5, odbyte: 4, no_show: 1, odwolane: 0, no_show_proc: 20, vip_auto: false },
  historia: history || [{ reservation_id: reservationId, data: '2026-08-21', godz_od: '18:00', liczba_osob: 4, status: 'potwierdzona' }],
  historia_total: 1,
  historia_limit: 50,
  ukryte_pola: canViewSensitive || canViewNotes ? [] : ['profil.alergie', 'profil.dieta', 'profil.notatka'],
  capabilities: {
    can_edit: canEdit,
    can_view_sensitive: canViewSensitive,
    can_view_internal_notes: canViewNotes,
  },
  zgody: consent || {
    state: 'missing',
    active: false,
    history: [],
    history_total: 0,
    current_document_version: 'marketing-2026-07-v1',
  },
})

beforeEach(() => {
  apiMock.mockReset()
  confirmMock.mockReset()
  keyMock.mockReset()
  keyMock.mockReturnValue('consent-key-1')
  confirmMock.mockResolvedValue(true)
  authState.isAdmin = true
  authState.permissions = new Set([
    'rezerwacje.dane_wrazliwe',
    'rezerwacje.notatki_wewnetrzne',
  ])
  privacyState.callback = null
  apiMock.mockImplementation((path, method = 'GET', body) => {
    if (path === '/crm/rezerwacje/42/profil' && method === 'GET') return Promise.resolve(response())
    if (path === '/crm/rezerwacje/42/profil' && method === 'PUT') {
      return Promise.resolve(response({ note: body.notatka }))
    }
    return Promise.reject(new Error(`Nieoczekiwane żądanie: ${method} ${path}`))
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('GuestProfileDialog', () => {
  it('ładuje i zapisuje profil admina wyłącznie przez opaque reservationId', async () => {
    const onSaved = vi.fn()
    const onDirtyChange = vi.fn()
    render(
      <GuestProfileDialog
        reservationId={42}
        onClose={vi.fn()}
        onSaved={onSaved}
        onDirtyChange={onDirtyChange}
      />,
    )

    const note = await screen.findByRole('textbox', { name: 'Notatka wewnętrzna' })
    expect(screen.getByRole('dialog', { name: /Karta gościa · Anna Kowalska/ })).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/crm/rezerwacje/42/profil', 'GET', null, expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )

    fireEvent.change(note, { target: { value: 'Prosi o stolik przy oknie' } })
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(true))
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz profil' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/crm/rezerwacje/42/profil',
      'PUT',
      expect.objectContaining({
        nazwisko: 'Anna Kowalska',
        tagi: ['stały', 'okno'],
        notatka: 'Prosi o stolik przy oknie',
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(await screen.findByText('Zapisano profil gościa.')).toBeInTheDocument()
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false))
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ profil_ref: 42 }))
    expect(apiMock.mock.calls.flat().join(' ')).not.toContain('600')
    expect(apiMock.mock.calls.flat().join(' ')).not.toContain('Kowalska/profil')
  })

  it('chroni brudny formularz przy Escape i zamknięciu', async () => {
    const onClose = vi.fn()
    confirmMock.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    render(<GuestProfileDialog reservationId={42} onClose={onClose} />)

    fireEvent.change(await screen.findByRole('textbox', { name: 'Notatka wewnętrzna' }), {
      target: { value: 'Niezapisana zmiana' },
    })
    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Odrzucić niezapisane zmiany'),
      expect.objectContaining({ confirmText: 'Odrzuć zmiany' }),
    ))
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Zamknij kartę gościa' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
    expect(onClose).toHaveBeenCalledWith({ dirtyConfirmed: true })
  })

  it('pokazuje nie-adminowi wariant tylko do odczytu oraz jawne redakcje', async () => {
    authState.isAdmin = false
    apiMock.mockResolvedValue(response({ canEdit: false, canViewSensitive: false, canViewNotes: false }))
    render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(await screen.findByText('Dane wrażliwe są ukryte zgodnie z uprawnieniami konta.')).toBeInTheDocument()
    expect(screen.getByText('Notatka wewnętrzna jest ukryta zgodnie z uprawnieniami konta.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zapisz profil' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByText('2026-08-21 · 18:00 · 4 os.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wróć' })).toHaveClass('min-h-11')
  })

  it('natychmiast redaguje otwartą kartę po cofnięciu praw i odświeża profil', async () => {
    authState.isAdmin = false
    apiMock.mockResolvedValueOnce(response({ canEdit: false }))
      .mockImplementationOnce(() => new Promise(() => {}))
    const { rerender } = render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(await screen.findByText('orzechy')).toBeInTheDocument()
    expect(screen.getByText('Lubi spokojny stolik')).toBeInTheDocument()

    authState.permissions = new Set()
    rerender(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(screen.queryByText('orzechy')).not.toBeInTheDocument()
    expect(screen.queryByText('Lubi spokojny stolik')).not.toBeInTheDocument()
    expect(screen.getByText('Dane wrażliwe są ukryte zgodnie z uprawnieniami konta.')).toBeInTheDocument()
    expect(screen.getByText('Notatka wewnętrzna jest ukryta zgodnie z uprawnieniami konta.')).toBeInTheDocument()
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
  })

  it('utrzymuje błąd w dialogu i pozwala ponowić odczyt', async () => {
    apiMock.mockRejectedValueOnce(new Error('Profil jest chwilowo niedostępny.'))
      .mockResolvedValueOnce(response())
    render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Profil jest chwilowo niedostępny.')
    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))

    expect(await screen.findByRole('textbox', { name: 'Notatka wewnętrzna' })).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('pokazuje kompletny rzeczywisty czas i zamrożony historyczny przydział', async () => {
    apiMock.mockResolvedValueOnce(response({
      history: [{
        reservation_id: 42,
        data: '2026-08-21',
        godz_od: '18:00',
        liczba_osob: 4,
        status: 'odbyla',
        planowany_czas_min: 120,
        rzeczywisty_czas_min: 92,
        odchylenie_min: -28,
        pomiar: 'complete',
        przydzial: {
          sala_id: 3,
          sala_nazwa: 'Sala główna',
          stoliki: [{ id: 1, nazwa: 'T1' }, { id: 2, nazwa: 'T2' }],
          kombinacja: { id: 8, wersja_id: 5, nazwa: 'Układ rodzinny' },
          proweniencja: 'frozen',
        },
      }],
    }))

    render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(await screen.findByText('92 min')).toBeInTheDocument()
    expect(screen.getByText(/plan 120 min · 28 min krócej/)).toBeInTheDocument()
    expect(screen.getByText('Sala główna · Konfiguracja: Układ rodzinny · Stoły: T1 + T2')).toBeInTheDocument()
  })

  it('jawnie oznacza brak pomiaru zamiast pokazywać zero', async () => {
    apiMock.mockResolvedValueOnce(response({
      history: [{
        reservation_id: 42,
        data: '2026-08-21',
        godz_od: '18:00',
        liczba_osob: 4,
        status: 'odbyla',
        planowany_czas_min: 90,
        rzeczywisty_czas_min: null,
        odchylenie_min: null,
        pomiar: 'missing',
        przydzial: { sala_id: null, sala_nazwa: null, stoliki: [], kombinacja: null, proweniencja: 'brak' },
      }],
    }))

    render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(await screen.findByText('Czas wizyty: brak pomiaru · plan 90 min')).toBeInTheDocument()
    expect(screen.queryByText('0 min')).not.toBeInTheDocument()
  })

  it('abortuje poprzedni profil i nie pokazuje spóźnionej odpowiedzi', async () => {
    let resolveOld
    let oldSignal
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path === '/crm/rezerwacje/1/profil' && method === 'GET') {
        oldSignal = options.signal
        return new Promise((resolve) => { resolveOld = resolve })
      }
      if (path === '/crm/rezerwacje/2/profil' && method === 'GET') {
        return Promise.resolve(response({ reservationId: 2, name: 'Nowy Gość' }))
      }
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
    const { rerender } = render(<GuestProfileDialog reservationId={1} onClose={vi.fn()} />)

    rerender(<GuestProfileDialog reservationId={2} onClose={vi.fn()} />)
    expect(await screen.findByText('Nowy Gość')).toBeInTheDocument()
    expect(oldSignal.aborted).toBe(true)

    await act(async () => { resolveOld(response({ reservationId: 1, name: 'Stary Gość' })) })
    expect(screen.queryByText('Stary Gość')).not.toBeInTheDocument()
  })

  it('przy purge usuwa PII, abortuje odczyt i zamyka kartę bez pytania o szkic', async () => {
    const onClose = vi.fn()
    let signal
    apiMock.mockImplementation((_path, _method, _body, options) => {
      signal = options.signal
      return Promise.resolve(response())
    })
    render(<GuestProfileDialog reservationId={42} onClose={onClose} />)
    await screen.findByRole('dialog', { name: /Karta gościa · Anna Kowalska/ })
    fireEvent.change(screen.getByRole('textbox', { name: 'Notatka wewnętrzna' }), {
      target: { value: 'Niezapisany szkic PII' },
    })
    const dirtyUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirtyUnload)
    expect(dirtyUnload.defaultPrevented).toBe(true)

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))

    expect(signal.aborted).toBe(true)
    expect(onClose).toHaveBeenCalledOnce()
    expect(confirmMock).not.toHaveBeenCalled()
    expect(screen.queryByText('Anna Kowalska')).not.toBeInTheDocument()
    const cleanUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(cleanUnload)
    expect(cleanUnload.defaultPrevented).toBe(false)
  })

  it('pozwala zapisać odmowę i blokuje wycofanie, gdy nie ma aktywnej zgody', async () => {
    apiMock.mockImplementation((path, method, body, options) => {
      if (path === '/crm/rezerwacje/42/profil' && method === 'GET') {
        return Promise.resolve(response())
      }
      if (path === '/crm/rezerwacje/42/zgody' && method === 'POST') {
        expect(body).toEqual({
          decision: 'decline',
          source: 'operator_phone',
          document_version: 'marketing-2026-07-v1',
        })
        expect(options.headers).toEqual({ 'Idempotency-Key': 'consent-key-1' })
        return Promise.resolve({
          state: 'declined',
          active: false,
          history: [{
            decision: 'decline',
            source: 'operator_phone',
            document_version: 'marketing-2026-07-v1',
            captured_at: '2026-07-23T12:00:00Z',
          }],
          current_document_version: 'marketing-2026-07-v1',
        })
      }
      return Promise.reject(new Error(`Nieoczekiwane żądanie: ${method} ${path}`))
    })

    render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(await screen.findByRole('button', { name: 'Wycofaj zgodę' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz odmowę' }))

    expect(await screen.findByText('Zapisano odmowę udzielenia zgody.')).toBeInTheDocument()
    expect(keyMock).toHaveBeenCalledOnce()
  })

  it('przy ponowieniu niejednoznacznego zapisu zgody używa tego samego klucza idempotencji', async () => {
    let consentAttempts = 0
    const usedKeys = []
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path === '/crm/rezerwacje/42/profil' && method === 'GET') {
        return Promise.resolve(response())
      }
      if (path === '/crm/rezerwacje/42/zgody' && method === 'POST') {
        consentAttempts += 1
        usedKeys.push(options.headers['Idempotency-Key'])
        if (consentAttempts === 1) return Promise.reject(new Error('Połączenie zostało przerwane'))
        return Promise.resolve({
          state: 'granted',
          active: true,
          history: [],
          current_document_version: 'marketing-2026-07-v1',
        })
      }
      return Promise.reject(new Error(`Nieoczekiwane żądanie: ${method} ${path}`))
    })

    render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)
    const grant = await screen.findByRole('button', { name: 'Zapisz zgodę' })

    fireEvent.click(grant)
    expect(await screen.findByRole('alert')).toHaveTextContent('Połączenie zostało przerwane')
    fireEvent.click(grant)

    await waitFor(() => expect(consentAttempts).toBe(2))
    expect(usedKeys).toEqual(['consent-key-1', 'consent-key-1'])
    expect(keyMock).toHaveBeenCalledOnce()
  })

  it('interpretuje czas zgody bez strefy jako UTC i pokazuje go w strefie Warszawy', async () => {
    apiMock.mockResolvedValue(response({
      consent: {
        state: 'granted',
        active: true,
        history: [{
          decision: 'grant',
          source: 'operator_phone',
          document_version: 'marketing-2026-07-v1',
          captured_at: '2026-07-23T12:00:00',
        }],
        current_document_version: 'marketing-2026-07-v1',
      },
    }))

    render(<GuestProfileDialog reservationId={42} onClose={vi.fn()} />)

    expect(await screen.findByText(/23\.07\.2026.*14:00/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zapisz odmowę' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Wycofaj zgodę' })).toBeEnabled()
  })
})
