// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, confirmMock, reloadDictsMock, setWeekMock, toastMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  reloadDictsMock: vi.fn(),
  setWeekMock: vi.fn(),
  toastMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/DataContext', () => ({
  useData: () => ({
    pracownicy: [{ id: 1, imie: 'Anna', nazwisko: 'Nowak', aktywny: true, kolor: null }],
    week: '2026-07-15|2026-07-21',
    przyszly: '2026-07-15|2026-07-21',
    setWeek: setWeekMock,
    reloadDicts: reloadDictsMock,
  }),
}))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock, confirm: confirmMock }) }))
vi.mock('../ui/WeekSelect', () => ({
  WeekSelect: ({ disabled }) => <select aria-label="Wybierz okres grafiku" disabled={disabled}><option>Przyszły tydzień</option></select>,
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }) => <>{children}</>,
  motion: {
    div: ({ children, initial, animate, exit, transition, ...props }) => <div {...props}>{children}</div>,
  },
}))

import Dyspozycje from './Dyspozycje'

const AVAILABILITY = {
  id: 5,
  pracownik_id: 1,
  data: '2026-07-15',
  dostepnosc: true,
  godz_od: null,
  godz_do: null,
}

function cell(status) {
  return screen.getByRole('button', { name: new RegExp(`^Anna Nowak, Środa 15\\.07\\.2026: ${status}`) })
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  confirmMock.mockResolvedValue(true)
  reloadDictsMock.mockResolvedValue(undefined)
})

describe('Dyspozycje administratora', () => {
  it('opisuje komórki pełnym kontekstem i otwiera dostępny edytor', async () => {
    apiMock.mockImplementation((path) => path.startsWith('/dyspozycje?') ? Promise.resolve([AVAILABILITY]) : Promise.resolve({}))
    render(<Dyspozycje />)

    const trigger = await screen.findByRole('button', { name: /Anna Nowak.*dostępny/ })
    expect(trigger.className).toContain('min-h-11')
    fireEvent.click(trigger)

    expect(screen.getByRole('dialog', { name: 'Anna Nowak' })).toBeInTheDocument()
    const close = screen.getByRole('button', { name: 'Zamknij edycję dyspozycyjności' })
    expect(close.className).toContain('min-h-11')
    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeDisabled()
  })

  it('zachowuje dane po błędzie, blokuje duplikat i aktualizuje komórkę po retry', async () => {
    let rejectFirst
    let attempts = 0
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/dyspozycje?')) return Promise.resolve([])
      if (path === '/dyspozycje' && method === 'POST') {
        attempts += 1
        if (attempts === 1) return new Promise((resolve, reject) => { rejectFirst = reject })
        return Promise.resolve(AVAILABILITY)
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<Dyspozycje />)
    const trigger = await screen.findByRole('button', { name: /^Anna Nowak, Środa 15\.07\.2026: brak zgłoszenia/ })
    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }))

    const pending = await screen.findByRole('button', { name: 'Zapisuję…' })
    expect(pending).toBeDisabled()
    fireEvent.click(pending)
    expect(attempts).toBe(1)
    expect(trigger).toBeInTheDocument()

    await act(async () => rejectFirst(new Error('Brak połączenia.')))

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia.')
    expect(screen.getByRole('dialog', { name: 'Anna Nowak' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Ponów zapis' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(cell('dostępny')).toBeInTheDocument()
    expect(screen.getByText(/Zapisano: Anna Nowak/)).toBeInTheDocument()
    expect(attempts).toBe(2)
    expect(apiMock.mock.calls.filter(([path]) => path.startsWith('/dyspozycje?'))).toHaveLength(1)
  })

  it('ostrzega przed zamknięciem zmienionego edytora i oddaje fokus po rezygnacji', async () => {
    apiMock.mockImplementation((path) => path.startsWith('/dyspozycje?') ? Promise.resolve([AVAILABILITY]) : Promise.resolve({}))
    confirmMock.mockResolvedValue(false)
    render(<Dyspozycje />)

    const trigger = await screen.findByRole('button', { name: /Anna Nowak.*dostępny/ })
    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole('button', { name: 'Niedostępny' }))
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij edycję dyspozycyjności' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Odrzucić niezapisane zmiany'),
      expect.objectContaining({ confirmText: 'Odrzuć zmiany' }),
    ))
    expect(screen.getByRole('dialog', { name: 'Anna Nowak' })).toBeInTheDocument()

    confirmMock.mockResolvedValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('czyści zgłoszenie natychmiast i pozwala je przywrócić', async () => {
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/dyspozycje?')) return Promise.resolve([AVAILABILITY])
      if (path === `/dyspozycje/${AVAILABILITY.id}` && method === 'DELETE') return Promise.resolve(null)
      if (path === '/dyspozycje' && method === 'POST') return Promise.resolve({ ...AVAILABILITY, id: 9 })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<Dyspozycje />)
    fireEvent.click(await screen.findByRole('button', { name: /Anna Nowak.*dostępny/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Wyczyść zgłoszenie dyspozycyjności' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(cell('brak zgłoszenia')).toBeInTheDocument()
    const undoOptions = toastMock.mock.calls.find(([, type, options]) => type === 'info' && options?.action)?.[2]
    expect(undoOptions?.action?.label).toBe('Cofnij')

    await act(async () => undoOptions.action.onClick())

    expect(cell('dostępny')).toBeInTheDocument()
    expect(screen.getByText(/Przywrócono: Anna Nowak/)).toBeInTheDocument()
  })

  it('po błędzie wczytania blokuje tabelę i oferuje lokalny retry', async () => {
    let attempts = 0
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/dyspozycje?')) {
        attempts += 1
        return attempts === 1 ? Promise.reject(new Error('Serwer niedostępny.')) : Promise.resolve([])
      }
      return Promise.resolve({})
    })

    render(<Dyspozycje />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Serwer niedostępny.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))

    expect(await screen.findByRole('button', { name: /^Anna Nowak, Środa 15\.07\.2026: brak zgłoszenia/ })).toBeInTheDocument()
  })
})
