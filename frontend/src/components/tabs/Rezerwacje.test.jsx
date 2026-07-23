// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden="true" /> }))

import Rezerwacje from './Rezerwacje'

const SNAPSHOT = {
  dni: [{
    data: '2026-07-11',
    liczba: 3,
    osoby: 8,
    godziny: [
      { godzina: '00:15', liczba: 1, osoby: 2 },
      { godzina: '00:45', liczba: 2, osoby: 6 },
    ],
  }],
}

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('Kompaktowy widok rezerwacji', () => {
  beforeEach(() => {
    const RealDate = Date
    const now = new RealDate('2026-07-10T22:30:00.000Z')
    vi.stubGlobal('Date', class extends RealDate {
      constructor(...args) {
        return args.length ? new RealDate(...args) : new RealDate(now)
      }

      static now() {
        return now.getTime()
      }
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('pokazuje osobny stan pierwszego ładowania i wyznacza dzisiaj w strefie Europe/Warsaw', async () => {
    const request = deferred()
    apiMock.mockReturnValueOnce(request.promise)

    render(<Rezerwacje />)

    expect(screen.getByRole('status', { name: 'Ładowanie rezerwacji' })).toHaveTextContent('Ładuję rezerwacje…')
    expect(screen.getByText('—')).toBeInTheDocument()

    await act(async () => request.resolve(SNAPSHOT))

    const today = screen.getByRole('button', { name: /Sobota.*11\.07.*3.*8 os\./ })
    expect(today).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('dziś')).toBeInTheDocument()
    expect(screen.getByText('2', { selector: '.font-display' })).toBeInTheDocument()
    expect(screen.queryByText(/kalendarz/i)).not.toBeInTheDocument()
  })

  it('nie przedstawia błędu pierwszego odczytu jako pustej listy i pozwala ponowić', async () => {
    apiMock
      .mockRejectedValueOnce(new Error('Brak połączenia'))
      .mockResolvedValueOnce({ dni: [] })

    render(<Rezerwacje />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się pobrać rezerwacji')
    expect(screen.getByRole('alert')).toHaveTextContent('Brak połączenia')
    expect(screen.queryByText('Brak rezerwacji na najbliższe 30 dni')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))

    expect(await screen.findByText('Brak rezerwacji na najbliższe 30 dni')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('zachowuje ostatni snapshot podczas odświeżania i po jego błędzie', async () => {
    const refresh = deferred()
    apiMock
      .mockResolvedValueOnce(SNAPSHOT)
      .mockReturnValueOnce(refresh.promise)

    render(<Rezerwacje />)

    const day = await screen.findByRole('button', { name: /Sobota.*11\.07.*3.*8 os\./ })
    fireEvent.click(screen.getByRole('button', { name: 'Odśwież rezerwacje' }))

    expect(day).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Aktualizuję listę…')
    expect(screen.getByRole('button', { name: 'Odświeżam rezerwacje' })).toBeDisabled()

    await act(async () => refresh.reject(new Error('Serwer jest chwilowo niedostępny')))

    expect(screen.getByRole('button', { name: /Sobota.*11\.07.*3.*8 os\./ })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Pokazuję ostatnie poprawnie pobrane dane')
    expect(screen.getByRole('alert')).toHaveTextContent('Serwer jest chwilowo niedostępny')
  })

  it('traktuje niepełną odpowiedź API jako błąd, a nie brak rezerwacji', async () => {
    apiMock.mockResolvedValueOnce({})

    render(<Rezerwacje />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Serwer zwrócił niepełne dane rezerwacji')
    expect(screen.queryByText('Brak rezerwacji na najbliższe 30 dni')).not.toBeInTheDocument()
  })

  it('usuwa zwinięte szczegóły dnia z drzewa dostępności i przywraca je po otwarciu', async () => {
    apiMock.mockResolvedValueOnce({
      dni: [
        ...SNAPSHOT.dni,
        {
          data: '2026-07-12',
          liczba: 1,
          osoby: 4,
          godziny: [{ godzina: '19:30', liczba: 1, osoby: 4 }],
        },
      ],
    })

    render(<Rezerwacje />)

    const futureDay = await screen.findByRole('button', { name: /Niedziela.*12\.07.*1.*4 os\./ })
    const details = document.getElementById('rezerwacje-dzien-2026-07-12')
    expect(futureDay).toHaveAttribute('aria-expanded', 'false')
    expect(details).toHaveAttribute('aria-hidden', 'true')
    expect(details).toHaveAttribute('inert')

    fireEvent.click(futureDay)

    expect(futureDay).toHaveAttribute('aria-expanded', 'true')
    expect(details).toHaveAttribute('aria-hidden', 'false')
    expect(details).not.toHaveAttribute('inert')
  })
})
