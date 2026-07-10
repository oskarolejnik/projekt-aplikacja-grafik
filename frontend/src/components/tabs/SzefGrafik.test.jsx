// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, reloadDictsMock, toastMock, dataState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  reloadDictsMock: vi.fn(),
  toastMock: vi.fn(),
  dataState: {
    week: '2026-07-06|2026-07-12',
    weeks: [{ value: '2026-07-06|2026-07-12', label: 'Bieżący tydzień' }],
    stanowiska: [
      { id: 1, nazwa: 'Sala' },
      { id: 2, nazwa: 'Bar' },
    ],
    pracownicy: [
      { id: 10, imie: 'Anna', nazwisko: 'Nowak' },
      { id: 11, imie: 'Jan', nazwisko: 'Kowalski' },
      { id: 12, imie: 'Ewa', nazwisko: 'Jutro' },
    ],
  },
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/DataContext', () => ({
  useData: () => ({
    ...dataState,
    setWeek: vi.fn(),
    reloadDicts: reloadDictsMock,
  }),
}))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import SzefGrafik from './SzefGrafik'

const OPUBLIKOWANY = {
  opublikowany: true,
  opublikowano_at: '2026-07-09T12:00:00',
  przydzialy: [
    { id: 1, data: '2026-07-10', pracownik_id: 10, stanowisko_id: 1, godz_od: '16:00:00', rewir: 'Parter' },
    { id: 2, data: '2026-07-10', pracownik_id: 11, stanowisko_id: 2, godz_od: null, rewir: null },
    { id: 3, data: '2026-07-11', pracownik_id: 12, stanowisko_id: 1, godz_od: '12:00:00', rewir: null },
  ],
  alerty_dzis: [{ data: '2026-07-10', stanowisko: 'Sala', wymagane: 2, obsadzone: 1, brakuje: 1 }],
  razem_brakuje_dzis: 1,
}

describe('SzefGrafik today-first', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-07-10T12:00:00'))
    reloadDictsMock.mockResolvedValue({})
    apiMock.mockResolvedValue(OPUBLIKOWANY)
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it('najpierw pokazuje dzisiejszą obsadę, uwagi i przejście do sali na żywo', async () => {
    const onOpenLive = vi.fn()
    render(<SzefGrafik onOpenLive={onOpenLive} />)

    await screen.findByRole('heading', { name: 'Piątek, 10 lipca' })
    expect(screen.getByText('2 osoby · 2 stanowiska')).toBeInTheDocument()
    expect(screen.getByText(/Sala: brakuje 1/)).toBeInTheDocument()
    expect(screen.getByText(/1 zmiana nie ma godziny rozpoczęcia/)).toBeInTheDocument()
    expect(screen.getByText('Anna Nowak')).toBeInTheDocument()
    expect(screen.getByText('Do ustalenia')).toBeInTheDocument()
    expect(screen.getByText('Pozostałe dni okresu')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Piątek, 10 lipca' }).compareDocumentPosition(
      screen.getByText('Pozostałe dni okresu'),
    ) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Sala na żywo/ }))
    expect(onOpenLive).toHaveBeenCalledOnce()
    expect(apiMock).toHaveBeenCalledWith('/szef/grafik?start=2026-07-06&end=2026-07-12')
    expect(apiMock.mock.calls.some(([path]) => path.startsWith('/przydzialy'))).toBe(false)
  })

  it('nie renderuje danych szkicu, gdy okres nie jest opublikowany', async () => {
    apiMock.mockResolvedValue({
      opublikowany: false,
      opublikowano_at: null,
      przydzialy: [],
      alerty_dzis: [],
      razem_brakuje_dzis: 0,
    })

    render(<SzefGrafik />)

    await screen.findByText('Grafik na ten okres nie został jeszcze opublikowany.')
    expect(screen.queryByText('Anna Nowak')).not.toBeInTheDocument()
    expect(screen.queryByText('Wymaga uwagi')).not.toBeInTheDocument()
  })

  it('odróżnia błąd pobierania od braku publikacji i pozwala ponowić', async () => {
    apiMock.mockRejectedValueOnce(new Error('Brak połączenia'))
    render(<SzefGrafik />)

    await screen.findByText(/Nie udało się pobrać grafiku.*Brak połączenia/)
    expect(screen.queryByText(/nie został jeszcze opublikowany/)).not.toBeInTheDocument()

    apiMock.mockResolvedValue(OPUBLIKOWANY)
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Piątek, 10 lipca' })).toBeInTheDocument())
  })

  it('odświeża słowniki podczas cichego pollingu bez blokowania grafiku', async () => {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    render(<SzefGrafik />)
    await screen.findByRole('heading', { name: 'Piątek, 10 lipca' })

    reloadDictsMock.mockClear()
    reloadDictsMock.mockReturnValue(new Promise(() => {}))
    apiMock.mockResolvedValueOnce({
      opublikowany: false,
      opublikowano_at: null,
      przydzialy: [],
      alerty_dzis: [],
      razem_brakuje_dzis: 0,
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000)
    })

    expect(reloadDictsMock).toHaveBeenCalledOnce()
    await screen.findByText('Grafik na ten okres nie został jeszcze opublikowany.')
  })
})
