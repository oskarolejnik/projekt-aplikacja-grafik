// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, setWeekMock, toastMock, dataState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  setWeekMock: vi.fn(),
  toastMock: vi.fn(),
  dataState: {
    current: {
      week: '2026-07-06|2026-07-12',
      biezacy: '2026-07-06|2026-07-12',
      przyszly: '2026-07-13|2026-07-19',
    },
  },
}))

vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../context/DataContext', () => ({
  useData: () => ({ ...dataState.current, setWeek: setWeekMock }),
}))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../components/ui/WeekSelect', () => ({ WeekSelect: () => <div>Wybór tygodnia</div> }))
vi.mock('../components/ui/Card', () => ({
  Card: ({ children, className = '', ...props }) => <div className={className} {...props}>{children}</div>,
}))
vi.mock('../components/ui/Spinner', () => ({ Spinner: () => <span>Ładowanie</span> }))
vi.mock('../components/ui/Banner', () => ({ Banner: ({ children }) => <div>{children}</div> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../components/RozliczImpreze', () => ({ default: () => null }))
vi.mock('../components/RozliczSale', () => ({ default: () => null }))

import EmployeeSchedule from './EmployeeSchedule'

const dataWzgledna = (delta) => {
  const d = new Date()
  d.setDate(d.getDate() + delta)
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
}

const zmiana = (data, godz_od, patch = {}) => ({
  data,
  godz_od,
  stanowisko: 'Sala',
  rewir: 'Parter',
  zamyka: false,
  zamyka_rewir: false,
  rozlicza_imprize: false,
  wspolpracownicy: [],
  ...patch,
})

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-07-10T16:00:00'))
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('EmployeeSchedule', () => {
  it('pokazuje dzisiejszą zmianę przed pełnym grafikiem', async () => {
    apiMock.mockResolvedValue({
      opublikowany: true,
      opublikowano_at: '2026-07-10T08:00:00',
      rozliczenia_oczekujace: [],
      zmiany: [
        zmiana(dataWzgledna(1), '12:00', { stanowisko: 'Bar' }),
        zmiana(dataWzgledna(-1), '10:00'),
        zmiana(dataWzgledna(0), '08:00', { stanowisko: 'Śniadania' }),
        zmiana(dataWzgledna(0), '18:00'),
      ],
    })
    const onSeen = vi.fn()

    render(<EmployeeSchedule onSeen={onSeen} />)

    await act(async () => {})
    const heading = screen.getByRole('heading', { name: 'Dzisiejsza zmiana' })
    const hero = heading.closest('section')
    expect(hero).not.toBeNull()
    expect(within(hero).getByText('18:00')).toBeInTheDocument()
    expect(within(hero).getByText('Sala')).toBeInTheDocument()
    expect(within(hero).getByText('Parter')).toBeInTheDocument()
    expect(onSeen).toHaveBeenCalledWith('2026-07-10T08:00:00')
  })

  it('czytelnie komunikuje brak ustalonej godziny najbliższej zmiany', async () => {
    apiMock.mockResolvedValue({
      opublikowany: true,
      opublikowano_at: null,
      rozliczenia_oczekujace: [],
      zmiany: [zmiana(dataWzgledna(1), null)],
    })

    render(<EmployeeSchedule />)

    await act(async () => {})
    const heading = screen.getByRole('heading', { name: 'Najbliższa zmiana' })
    expect(within(heading.closest('section')).getByText('Godzina do ustalenia')).toBeInTheDocument()
  })

  it('prowadzi do następnego tygodnia także wtedy, gdy nie ma żadnej zmiany', async () => {
    apiMock.mockResolvedValue({
      opublikowany: true,
      opublikowano_at: null,
      rozliczenia_oczekujace: [],
      zmiany: [],
    })

    render(<EmployeeSchedule />)
    await act(async () => {})

    expect(screen.queryByRole('heading', { name: /zmiana/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż następny tydzień' }))
    expect(setWeekMock).toHaveBeenCalledWith('2026-07-13|2026-07-19')
  })
})
