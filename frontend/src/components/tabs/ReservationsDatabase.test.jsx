// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../lib/icons', () => ({
  Icon: ({ name }) => <span aria-hidden="true">{name}</span>,
}))

import ReservationsDatabase from './ReservationsDatabase'

const baseRoute = {
  from: '2026-07-01',
  to: '2026-09-30',
  status: '',
  sort: 'data_desc',
  offset: 0,
}

const reservation = {
  id: 71,
  data: '2026-08-19',
  godz_od: '19:00',
  nazwisko: 'Kowalska',
  telefon: '600 123 456',
  liczba_osob: 5,
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
  apiMock.mockResolvedValue({ rezerwacje: [], total: 0 })
  window.history.replaceState({}, '', '#/rezerwacje/baza?od=2026-07-01&do=2026-09-30')
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/')
})

describe('ReservationsDatabase', () => {
  it('wysyła nazwisko lub telefon tylko w ciele POST i nie dopisuje PII do URL', async () => {
    render(<ReservationsDatabase route={baseRoute} />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwisko lub telefon' }), {
      target: { value: 'Kowalska 600 123 456' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Szukaj' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(apiMock).toHaveBeenLastCalledWith(
      '/rezerwacje-stolik/wyszukaj',
      'POST',
      {
        start: '2026-07-01',
        end: '2026-09-30',
        query: 'Kowalska 600 123 456',
        status: null,
        sort: 'data_desc',
        offset: 0,
        limit: 25,
      },
      { signal: expect.any(AbortSignal) },
    )
    expect(window.location.href).not.toContain('Kowalska')
    expect(window.location.href).not.toContain('600')
  })

  it('wymaga co najmniej dwóch znaków i nie wysyła niepoprawnej frazy', async () => {
    render(<ReservationsDatabase route={baseRoute} />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))

    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwisko lub telefon' }), {
      target: { value: ' K ' },
    })
    fireEvent.submit(screen.getByRole('search'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Wpisz co najmniej 2 znaki')
    expect(apiMock).toHaveBeenCalledTimes(1)
  })

  it('przekazuje zakres, status, sortowanie i paginację bez gubienia offsetu', async () => {
    const onContextChange = vi.fn()
    const route = {
      ...baseRoute,
      status: 'potwierdzona',
      sort: 'nazwisko_asc',
      offset: 25,
    }
    apiMock.mockResolvedValue({ rezerwacje: [reservation], total: 60 })

    render(
      <ReservationsDatabase
        route={route}
        onContextChange={onContextChange}
      />,
    )

    await waitFor(() => {
      expect(apiMock).toHaveBeenCalledWith(
        '/rezerwacje-stolik/wyszukaj',
        'POST',
        {
          start: '2026-07-01',
          end: '2026-09-30',
          query: null,
          status: 'potwierdzona',
          sort: 'nazwisko_asc',
          offset: 25,
          limit: 25,
        },
        { signal: expect.any(AbortSignal) },
      )
    })
    expect(screen.getByText('26–26 z 60')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Od'), { target: { value: '2026-08-01' } })
    expect(onContextChange).toHaveBeenCalledWith(
      { from: '2026-08-01', offset: 0 },
      { replace: true },
    )

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'no_show' } })
    expect(onContextChange).toHaveBeenCalledWith(
      { status: 'no_show', offset: 0 },
      { replace: true },
    )

    fireEvent.change(screen.getByLabelText('Sortowanie'), { target: { value: 'data_asc' } })
    expect(onContextChange).toHaveBeenCalledWith(
      { sort: 'data_asc', offset: 0 },
      { replace: true },
    )

    fireEvent.click(screen.getByRole('button', { name: 'Poprzednia' }))
    expect(onContextChange).toHaveBeenCalledWith({ offset: 0 })
    fireEvent.click(screen.getByRole('button', { name: 'Następna' }))
    expect(onContextChange).toHaveBeenCalledWith({ offset: 50 })
  })

  it('anuluje stare wyszukiwanie i ignoruje jego odpowiedź po zmianie filtrów', async () => {
    const first = deferred()
    const second = deferred()
    apiMock
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const { rerender } = render(<ReservationsDatabase route={baseRoute} />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    const firstSignal = apiMock.mock.calls[0][3].signal

    rerender(
      <ReservationsDatabase
        route={{ ...baseRoute, status: 'potwierdzona' }}
      />,
    )
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    expect(firstSignal.aborted).toBe(true)

    await act(async () => {
      second.resolve({
        rezerwacje: [{ ...reservation, id: 82, nazwisko: 'Nowsza' }],
        total: 1,
      })
    })
    expect(await screen.findByText('Nowsza')).toBeInTheDocument()

    await act(async () => {
      first.resolve({
        rezerwacje: [{ ...reservation, id: 83, nazwisko: 'Starsza' }],
        total: 1,
      })
    })
    expect(screen.queryByText('Starsza')).not.toBeInTheDocument()
    expect(screen.getByText('Nowsza')).toBeInTheDocument()
  })

  it('nie pokazuje starych danych osobowych pod nowym filtrem', async () => {
    apiMock.mockResolvedValueOnce({ rezerwacje: [reservation], total: 1 })
    const next = deferred()
    apiMock.mockReturnValueOnce(next.promise)
    const { rerender } = render(<ReservationsDatabase route={baseRoute} />)
    expect(await screen.findByText('Kowalska')).toBeInTheDocument()

    rerender(<ReservationsDatabase route={{ ...baseRoute, status: 'no_show' }} />)

    expect(screen.queryByText('Kowalska')).not.toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Ładowanie bazy rezerwacji' })).toBeInTheDocument()
    await act(async () => next.resolve({ rezerwacje: [], total: 0 }))
    expect(await screen.findByText('Brak pasujących rezerwacji')).toBeInTheDocument()
  })

  it('pokazuje błąd z retry, a dopiero poprawna pusta odpowiedź uruchamia pusty stan', async () => {
    apiMock
      .mockRejectedValueOnce(new Error('Nie udało się pobrać bazy.'))
      .mockResolvedValueOnce({ rezerwacje: [], total: 0 })

    render(<ReservationsDatabase route={baseRoute} />)

    expect(await screen.findByText('Nie udało się pobrać bazy.')).toBeInTheDocument()
    expect(screen.queryByText('Brak pasujących rezerwacji')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))

    expect(await screen.findByText('Brak pasujących rezerwacji')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('Nie udało się pobrać bazy.')).not.toBeInTheDocument()
  })

  it('otwiera wskazany rekord z pełnym kontekstem rezerwacji', async () => {
    const onOpenReservation = vi.fn()
    apiMock.mockResolvedValue({ rezerwacje: [reservation], total: 1 })

    render(
      <ReservationsDatabase
        route={baseRoute}
        onOpenReservation={onOpenReservation}
      />,
    )

    fireEvent.click(await screen.findByRole('button', {
      name: 'Otwórz rezerwację: Kowalska, 2026-08-19',
    }))
    expect(onOpenReservation).toHaveBeenCalledWith(reservation)
  })
})
