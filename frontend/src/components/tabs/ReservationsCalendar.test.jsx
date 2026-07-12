// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../lib/icons', () => ({
  Icon: ({ name }) => <span aria-hidden="true">{name}</span>,
}))

import ReservationsCalendar from './ReservationsCalendar'

const reservation = {
  id: 41,
  data: '2026-08-19',
  godz_od: '18:30',
  nazwisko: 'Kowalska',
  liczba_osob: 4,
  status: 'potwierdzona',
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockResolvedValue({ rezerwacje: [] })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ReservationsCalendar', () => {
  it('pobiera pełny tydzień, pokazuje siedem dni i otwiera dzień oraz rekord', async () => {
    const onOpenDay = vi.fn()
    const onOpenReservation = vi.fn()
    apiMock.mockResolvedValue({ rezerwacje: [reservation] })

    render(
      <ReservationsCalendar
        date="2026-08-19"
        onOpenDay={onOpenDay}
        onOpenReservation={onOpenReservation}
      />,
    )

    const recordButton = await screen.findByRole('button', {
      name: 'Otwórz rezerwację 18:30, Kowalska',
    })
    expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje-stolik?start=2026-08-17&end=2026-08-23',
      'GET',
      null,
      { signal: expect.any(AbortSignal) },
    )
    expect(screen.getAllByRole('button', { name: 'Otwórz dzień' })).toHaveLength(7)
    expect(screen.getByText('Potwierdzona')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: 'Otwórz dzień' })[2])
    expect(onOpenDay).toHaveBeenCalledWith('2026-08-19')

    fireEvent.click(recordButton)
    expect(onOpenReservation).toHaveBeenCalledWith(reservation)
  })

  it('w trybie dnia pobiera tylko wybraną datę i przekazuje zmianę zakresu oraz statusu', async () => {
    const onContextChange = vi.fn()

    render(
      <ReservationsCalendar
        date="2026-08-19"
        mode="day"
        status="potwierdzona"
        onContextChange={onContextChange}
      />,
    )

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith(
        '/rezerwacje-stolik?start=2026-08-19&end=2026-08-19&status=potwierdzona',
        'GET',
        null,
        { signal: expect.any(AbortSignal) },
      )
    })
    expect(screen.getAllByRole('button', { name: 'Otwórz dzień' })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Dzień' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Dzień' })).toHaveClass('min-h-11')

    fireEvent.click(screen.getByRole('button', { name: 'Tydzień' }))
    expect(onContextChange).toHaveBeenCalledWith({ mode: 'week' })

    fireEvent.change(screen.getByLabelText('Status rezerwacji'), {
      target: { value: 'no_show' },
    })
    expect(onContextChange).toHaveBeenCalledWith({ status: 'no_show' })
  })

  it('anuluje poprzedni zakres i ignoruje jego spóźnioną odpowiedź po zmianie daty', async () => {
    const first = deferred()
    const second = deferred()
    apiMock
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const { rerender } = render(<ReservationsCalendar date="2026-08-17" />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    const firstSignal = apiMock.mock.calls[0][3].signal

    rerender(<ReservationsCalendar date="2026-08-24" />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(firstSignal.aborted).toBe(true)

    await act(async () => {
      second.resolve({
        rezerwacje: [{ ...reservation, id: 52, data: '2026-08-24', nazwisko: 'Nowsza' }],
      })
    })
    expect(await screen.findByText('Nowsza')).toBeInTheDocument()

    await act(async () => {
      first.resolve({
        rezerwacje: [{ ...reservation, id: 53, data: '2026-08-17', nazwisko: 'Starsza' }],
      })
    })
    expect(screen.queryByText('Starsza')).not.toBeInTheDocument()
    expect(screen.getByText('Nowsza')).toBeInTheDocument()
  })

  it('nie pokazuje starego tygodnia pod nagłówkiem nowego zakresu', async () => {
    apiMock.mockResolvedValueOnce({ rezerwacje: [reservation] })
    const next = deferred()
    apiMock.mockReturnValueOnce(next.promise)
    const { rerender } = render(<ReservationsCalendar date="2026-08-19" />)
    expect(await screen.findByText('Kowalska')).toBeInTheDocument()

    rerender(<ReservationsCalendar date="2026-08-26" />)

    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Ładowanie kalendarza rezerwacji' })).toBeInTheDocument()
    await act(async () => next.resolve({ rezerwacje: [] }))
    expect(await screen.findAllByText('Bez rezerwacji')).toHaveLength(7)
  })

  it('bez prawa do szczegółów obiecuje wyłącznie otwarcie dnia', async () => {
    apiMock.mockResolvedValue({ rezerwacje: [reservation] })
    render(<ReservationsCalendar date="2026-08-19" canOpenDetails={false} />)

    expect(await screen.findByRole('button', { name: 'Otwórz dzień 2026-08-19, 18:30' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Otwórz rezerwację/ })).not.toBeInTheDocument()
  })

  it('odróżnia błąd od pustego tygodnia i po retry pokazuje poprawny pusty stan', async () => {
    apiMock
      .mockRejectedValueOnce(new Error('Serwer rezerwacji nie odpowiada.'))
      .mockResolvedValueOnce({ rezerwacje: [] })

    render(<ReservationsCalendar date="2026-08-19" />)

    expect(await screen.findByText('Serwer rezerwacji nie odpowiada.')).toBeInTheDocument()
    expect(screen.queryAllByText('Bez rezerwacji')).toHaveLength(0)

    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(await screen.findAllByText('Bez rezerwacji')).toHaveLength(7)
    expect(screen.queryByText('Serwer rezerwacji nie odpowiada.')).not.toBeInTheDocument()
  })
})
