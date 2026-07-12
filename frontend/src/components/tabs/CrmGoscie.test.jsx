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

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockResolvedValue([guest])
})

afterEach(() => cleanup())

describe('CrmGoscie', () => {
  it('otwiera wspólną kartę przez profil_ref bez surowego klucza CRM', async () => {
    render(<CrmGoscie />)

    const trigger = await screen.findByRole('button', { name: 'Otwórz kartę gościa: Anna Kowalska' })
    fireEvent.click(trigger)

    expect(screen.getByRole('dialog', { name: 'Testowa karta gościa' })).toHaveTextContent('Profil rezerwacji 817')
    expect(apiMock).toHaveBeenCalledWith(
      '/crm/goscie', 'GET', null, expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(trigger).toHaveClass('min-h-11')
  })

  it('odświeża listę w tle po zapisie i nie zamyka karty', async () => {
    render(<CrmGoscie />)
    fireEvent.click(await screen.findByRole('button', { name: 'Otwórz kartę gościa: Anna Kowalska' }))

    fireEvent.click(screen.getByRole('button', { name: 'Odśwież po zapisie' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(screen.getByRole('dialog', { name: 'Testowa karta gościa' })).toBeInTheDocument()
  })

  it('pokazuje lokalny błąd z retry zamiast fałszywego pustego stanu', async () => {
    apiMock.mockRejectedValueOnce(new Error('Brak połączenia z bazą gości.'))
      .mockResolvedValueOnce([guest])

    render(<CrmGoscie />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia z bazą gości.')
    expect(screen.queryByText(/Brak danych gości/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))

    expect(await screen.findByRole('button', { name: 'Otwórz kartę gościa: Anna Kowalska' })).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('purge usuwa listę PII, zamyka profil i odrzuca spóźnioną odpowiedź', async () => {
    let resolveGuests
    apiMock.mockImplementationOnce(() => new Promise((resolve) => { resolveGuests = resolve }))

    render(<CrmGoscie />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    const requestSignal = apiMock.mock.calls[0][3].signal

    act(() => {
      purgeReservationPrivacy({ reason: 'logout', broadcast: false })
    })

    expect(requestSignal.aborted).toBe(true)
    expect(screen.queryByText('Anna Kowalska')).not.toBeInTheDocument()

    await act(async () => {
      resolveGuests([guest])
      await Promise.resolve()
    })

    expect(screen.queryByText('Anna Kowalska')).not.toBeInTheDocument()
  })
})
