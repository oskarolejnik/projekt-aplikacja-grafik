// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'
import ReservationRecommendations from './ReservationRecommendations'

const apiMock = vi.fn()
const confirmMock = vi.fn()
const keyMock = vi.fn(() => 'reservation-recommendation-decision-test-key')

vi.mock('../../lib/api', () => ({
  api: (...args) => apiMock(...args),
  nowyKluczIdempotencji: (...args) => keyMock(...args),
}))

vi.mock('../ui/Toast', () => ({
  useToast: () => ({ confirm: confirmMock }),
}))

const RANGE = { start: '2026-04-01', end: '2026-06-30' }
const CANDIDATE = {
  hash: 'abc123recommendation',
  serwis: { id: 7, nazwa: 'Kolacja' },
  segment: '1-2',
  proba: 24,
  kompletnosc_proc: 80,
  dni_serwisu: 8,
  obecnie_min: 120,
  proponowane_min: 105,
  stan: 'pending',
}
const DATA = {
  rekomendacje: [CANDIDATE],
  progi: {
    minimalna_proba: 20,
    minimalna_kompletnosc_proc: 70,
    minimalne_dni_serwisu: 4,
  },
}
const SIMULATION = {
  simulation_hash: 'simulation-hash-1',
  summary: {
    sprawdzone_sloty: 80,
    dostepne_przed: 31,
    dostepne_po: 36,
    roznica: 5,
  },
}

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  apiMock.mockReset()
  confirmMock.mockReset()
  keyMock.mockClear()
})

afterEach(() => cleanup())

describe('ReservationRecommendations R7.4', () => {
  it('prowadzi konto analytics-only od dowodów do symulacji bez możliwości zmiany reguły', async () => {
    apiMock.mockResolvedValueOnce(SIMULATION)

    render(
      <ReservationRecommendations
        data={DATA}
        range={RANGE}
        canDecide={false}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Kolacja · grupa 1–2 os.' })).toBeInTheDocument()
    expect(screen.getByText('Pełne pomiary').parentElement).toHaveTextContent('24/20')
    expect(screen.getByText('Kompletność').parentElement).toHaveTextContent('80%')
    expect(screen.getByText('Dni serwisu').parentElement).toHaveTextContent('8/4')
    expect(screen.getByText('Proponowana zmiana').parentElement).toHaveTextContent('2 h')
    expect(screen.getByText('Proponowana zmiana').parentElement).toHaveTextContent('1 h 45 min')
    expect(screen.queryByRole('button', { name: 'Przyjmij zmianę' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź wpływ' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/analityka/rezerwacje/rekomendacje/abc123recommendation/symulacja',
      'POST',
      RANGE,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(await screen.findByText('Wpływ został policzony')).toBeInTheDocument()
    expect(screen.getByText('Sprawdzone sloty').parentElement).toHaveTextContent('80')
    expect(screen.getByText('Różnica').parentElement).toHaveTextContent('+5')
    expect(screen.getByText(/To snapshot dostępności, nie prognoza popytu/)).toBeInTheDocument()
    expect(screen.getByText(/Przyjęcie lub odrzucenie wymaga uprawnienia/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Przyjmij zmianę' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Odrzuć rekomendację' })).not.toBeInTheDocument()
  })

  it('wymaga jawnego potwierdzenia i zapisuje przyjęcie z hashem symulacji oraz idempotencją', async () => {
    const onChanged = vi.fn()
    apiMock
      .mockResolvedValueOnce(SIMULATION)
      .mockResolvedValueOnce({ stan: 'accepted' })
    confirmMock.mockResolvedValue(true)

    render(
      <ReservationRecommendations
        data={DATA}
        range={RANGE}
        canDecide
        onChanged={onChanged}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź wpływ' }))
    await screen.findByText('Wpływ został policzony')
    fireEvent.click(screen.getByRole('button', { name: 'Przyjmij zmianę' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Przyjąć zmianę czasu wizyty z 2 h na 1 h 45 min'),
      expect.objectContaining({
        title: 'Przyjąć rekomendację?',
        confirmText: 'Przyjmij zmianę',
        danger: false,
      }),
    ))
    await waitFor(() => expect(apiMock).toHaveBeenLastCalledWith(
      '/analityka/rezerwacje/rekomendacje/abc123recommendation/decyzja',
      'POST',
      {
        start: RANGE.start,
        end: RANGE.end,
        simulation_hash: 'simulation-hash-1',
        decyzja: 'accepted',
        powod: 'confirmed_after_simulation',
      },
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        headers: {
          'Idempotency-Key': 'reservation-recommendation-decision-test-key',
        },
      }),
    ))
    expect(await screen.findByText(/Rekomendacja została przyjęta/)).toBeInTheDocument()
    expect(screen.getByText(/istniejące rezerwacje pozostały bez zmian/)).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledWith({ stan: 'accepted' })
    expect(screen.queryByRole('button', { name: 'Przyjmij zmianę' })).not.toBeInTheDocument()
  })

  it('zapisuje typowany powód odrzucenia dopiero po symulacji i potwierdzeniu', async () => {
    apiMock
      .mockResolvedValueOnce(SIMULATION)
      .mockResolvedValueOnce({ stan: 'rejected' })
    confirmMock.mockResolvedValue(true)

    render(
      <ReservationRecommendations
        data={DATA}
        range={RANGE}
        canDecide
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź wpływ' }))
    await screen.findByText('Wpływ został policzony')
    fireEvent.change(screen.getByLabelText('Powód odrzucenia'), {
      target: { value: 'seasonal_sample' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Odrzuć rekomendację' }))

    await waitFor(() => expect(apiMock).toHaveBeenLastCalledWith(
      '/analityka/rezerwacje/rekomendacje/abc123recommendation/decyzja',
      'POST',
      expect.objectContaining({
        start: RANGE.start,
        end: RANGE.end,
        simulation_hash: 'simulation-hash-1',
        decyzja: 'rejected',
        powod: 'seasonal_sample',
      }),
      expect.objectContaining({
        headers: {
          'Idempotency-Key': 'reservation-recommendation-decision-test-key',
        },
      }),
    ))
    expect(await screen.findByText(/Rekomendacja została odrzucona/)).toBeInTheDocument()
    expect(screen.getByText(/Obecna reguła pozostaje bez zmian/)).toBeInTheDocument()
  })

  it('pokazuje lokalny błąd symulacji i pozwala ponowić bez utraty dowodów', async () => {
    apiMock
      .mockRejectedValueOnce(new Error('Symulator jest chwilowo niedostępny.'))
      .mockResolvedValueOnce(SIMULATION)

    render(
      <ReservationRecommendations
        data={DATA}
        range={RANGE}
        canDecide
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź wpływ' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Symulator jest chwilowo niedostępny.')
    expect(screen.getByText('Pełne pomiary').parentElement).toHaveTextContent('24/20')

    fireEvent.click(screen.getByRole('button', { name: 'Ponów symulację' }))
    expect(await screen.findByText('Wpływ został policzony')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('przy ponowieniu niejednoznacznej decyzji zachowuje ten sam klucz idempotencji', async () => {
    apiMock
      .mockResolvedValueOnce(SIMULATION)
      .mockRejectedValueOnce(new Error('Nie udało się potwierdzić wyniku.'))
      .mockResolvedValueOnce({ stan: 'accepted' })
    confirmMock.mockResolvedValue(true)

    render(
      <ReservationRecommendations
        data={DATA}
        range={RANGE}
        canDecide
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź wpływ' }))
    await screen.findByText('Wpływ został policzony')
    fireEvent.click(screen.getByRole('button', { name: 'Przyjmij zmianę' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się potwierdzić wyniku.')

    fireEvent.click(screen.getByRole('button', { name: 'Przyjmij zmianę' }))
    expect(await screen.findByText(/Rekomendacja została przyjęta/)).toBeInTheDocument()

    const decisionCalls = apiMock.mock.calls.filter(([path]) => path.endsWith('/decyzja'))
    expect(decisionCalls).toHaveLength(2)
    expect(decisionCalls[0][3].headers['Idempotency-Key']).toBe(
      decisionCalls[1][3].headers['Idempotency-Key'],
    )
    expect(keyMock).toHaveBeenCalledTimes(1)
  })

  it('abortuje symulację starego okresu i pokazuje neutralny pusty stan', async () => {
    const pending = deferred()
    apiMock.mockReturnValueOnce(pending.promise)
    const { rerender } = render(
      <ReservationRecommendations
        data={DATA}
        range={RANGE}
        canDecide
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź wpływ' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    const signal = apiMock.mock.calls[0][3].signal

    rerender(
      <ReservationRecommendations
        data={{ rekomendacje: [], progi: DATA.progi }}
        range={{ start: '2026-07-01', end: '2026-07-31' }}
        canDecide
      />,
    )

    expect(signal.aborted).toBe(true)
    await act(async () => pending.resolve(SIMULATION))
    expect(screen.queryByText('Wpływ został policzony')).not.toBeInTheDocument()
    expect(screen.getByText('Brak rekomendacji do decyzji')).toBeInTheDocument()
    expect(screen.getByText(/co najmniej 20 pełnych pomiarów/)).toBeInTheDocument()
  })
})
