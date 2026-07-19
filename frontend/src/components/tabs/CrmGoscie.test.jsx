// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'
import CrmGoscie from './CrmGoscie'
import { purgeReservationPrivacy } from '../../lib/reservationPrivacy'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('./GuestProfileDialog', () => ({
  default: ({ reservationId, onClose, onSaved }) => (
    <div role="dialog" aria-label="Testowa karta gościa">
      <span>Profil rezerwacji {reservationId}</span>
      <button type="button" onClick={onSaved}>Odśwież po zapisie</button>
      <button type="button" onClick={onClose}>Zamknij profil</button>
    </div>
  ),
}))

const guest = {
  profil_ref: 817,
  identity: { source: 'telefon', confident: true },
  nazwisko: 'Anna Kowalska',
  telefon: '600 700 800',
  email: null,
  wizyt: 4,
  odbyte: 3,
  no_show: 1,
  no_show_proc: 25,
  ryzyko: 'srednie',
  ostatnia_data: '2026-08-21',
  vip: true,
  ma_alergie: false,
  tagi: ['stały'],
}

const response = (guests = [guest], overrides = {}) => ({
  goscie: guests,
  total: guests.length,
  offset: 0,
  limit: 25,
  podsumowanie: {},
  ...overrides,
})

function deferred() {
  let resolve
  const promise = new Promise((resolvePromise) => { resolve = resolvePromise })
  return { promise, resolve }
}

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockResolvedValue(response())
  window.history.replaceState({}, '', '/?panel=crm')
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/')
})

describe('CrmGoscie R7.1', () => {
  it('wysyła filtry w body POST i nie zapisuje PII w adresie ani storage', async () => {
    render(<CrmGoscie />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))

    expect(apiMock).toHaveBeenLastCalledWith(
      '/crm/goscie/wyszukaj',
      'POST',
      {
        q: null,
        vip: null,
        ryzyko: null,
        min_wizyt: 1,
        sort: 'ostatnia_data_desc',
        offset: 0,
        limit: 25,
      },
      { signal: expect.any(AbortSignal) },
    )

    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwisko, telefon lub e-mail' }), {
      target: { value: 'Kowalska 600 700 800' },
    })
    fireEvent.submit(screen.getByRole('search'))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(apiMock.mock.calls[1][2]).toMatchObject({ q: 'Kowalska 600 700 800' })
    expect(window.location.href).not.toContain('Kowalska')
    expect(window.location.href).not.toContain('600')
    expect(JSON.stringify({ ...localStorage })).not.toContain('Kowalska')
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('Kowalska')
  })

  it('otwiera wspólną kartę przez profil_ref i odświeża bieżący kontekst po zapisie', async () => {
    render(<CrmGoscie />)

    const triggers = await screen.findAllByRole('button', { name: 'Otwórz kartę gościa: Anna Kowalska' })
    expect(triggers).toHaveLength(2)
    fireEvent.click(triggers[0])

    expect(screen.getByRole('dialog', { name: 'Testowa karta gościa' })).toHaveTextContent('Profil rezerwacji 817')
    fireEvent.click(screen.getByRole('button', { name: 'Odśwież po zapisie' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(screen.getByRole('dialog', { name: 'Testowa karta gościa' })).toBeInTheDocument()
    expect(apiMock.mock.calls[1][2]).toMatchObject({ q: null, offset: 0 })
  })

  it('abortuje stare wyszukiwanie i nie pokazuje jego spóźnionej odpowiedzi', async () => {
    const firstSearch = deferred()
    const secondSearch = deferred()
    apiMock
      .mockResolvedValueOnce(response())
      .mockReturnValueOnce(firstSearch.promise)
      .mockReturnValueOnce(secondSearch.promise)

    render(<CrmGoscie />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))

    const input = screen.getByRole('textbox', { name: 'Nazwisko, telefon lub e-mail' })
    fireEvent.change(input, { target: { value: 'Anna' } })
    fireEvent.submit(screen.getByRole('search'))
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    const staleSignal = apiMock.mock.calls[1][3].signal

    fireEvent.change(input, { target: { value: 'Ewa' } })
    fireEvent.submit(screen.getByRole('search'))
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(3))
    expect(staleSignal.aborted).toBe(true)

    await act(async () => {
      secondSearch.resolve(response([{ ...guest, profil_ref: 900, nazwisko: 'Ewa Nowak' }]))
    })
    expect((await screen.findAllByText('Ewa Nowak')).length).toBeGreaterThan(0)

    await act(async () => {
      firstSearch.resolve(response([{ ...guest, profil_ref: 901, nazwisko: 'Anna Spóźniona' }]))
    })
    expect(screen.queryByText('Anna Spóźniona')).not.toBeInTheDocument()
  })

  it('przekazuje filtry i paginację bez dopisywania ich do URL', async () => {
    apiMock.mockResolvedValue(response([guest], { total: 40 }))
    render(<CrmGoscie />)
    await screen.findAllByText('Anna Kowalska')

    fireEvent.change(screen.getByLabelText('VIP'), { target: { value: 'true' } })
    fireEvent.change(screen.getByLabelText('Ryzyko'), { target: { value: 'srednie' } })
    fireEvent.change(screen.getByLabelText('Minimum wizyt'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Sortowanie'), { target: { value: 'ryzyko_desc' } })

    await waitFor(() => expect(apiMock).toHaveBeenLastCalledWith(
      '/crm/goscie/wyszukaj',
      'POST',
      expect.objectContaining({ vip: true, ryzyko: 'srednie', min_wizyt: 3, sort: 'ryzyko_desc', offset: 0 }),
      { signal: expect.any(AbortSignal) },
    ))

    fireEvent.click(screen.getByRole('button', { name: 'Następna' }))
    await waitFor(() => expect(apiMock).toHaveBeenLastCalledWith(
      '/crm/goscie/wyszukaj',
      'POST',
      expect.objectContaining({ offset: 25 }),
      { signal: expect.any(AbortSignal) },
    ))
    expect(window.location.href).toBe('http://localhost:3000/?panel=crm')
  })

  it('pokazuje lokalny błąd z retry zamiast fałszywego pustego stanu', async () => {
    apiMock.mockRejectedValueOnce(new Error('Brak połączenia z bazą gości.'))
      .mockResolvedValueOnce(response())

    render(<CrmGoscie />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia z bazą gości.')
    expect(screen.queryByText('Brak pasujących gości')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))

    expect((await screen.findAllByRole('button', { name: 'Otwórz kartę gościa: Anna Kowalska' })).length).toBeGreaterThan(0)
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('purge usuwa PII, czyści frazę, zamyka profil i odrzuca spóźnioną odpowiedź', async () => {
    const pending = deferred()
    apiMock.mockReturnValueOnce(pending.promise)

    render(<CrmGoscie />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    const requestSignal = apiMock.mock.calls[0][3].signal
    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwisko, telefon lub e-mail' }), {
      target: { value: 'Sekretna osoba' },
    })

    act(() => {
      purgeReservationPrivacy({ reason: 'logout', broadcast: false })
    })

    expect(requestSignal.aborted).toBe(true)
    expect(screen.getByRole('textbox', { name: 'Nazwisko, telefon lub e-mail' })).toHaveValue('')
    expect(screen.queryByText('Anna Kowalska')).not.toBeInTheDocument()

    await act(async () => {
      pending.resolve(response())
      await Promise.resolve()
    })

    expect(screen.queryByText('Anna Kowalska')).not.toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(1)
  })
})
