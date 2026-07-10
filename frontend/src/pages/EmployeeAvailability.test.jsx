// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, confirmMock, setWeekMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  setWeekMock: vi.fn(),
}))

vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../context/DataContext', () => ({
  useData: () => ({
    week: '2026-07-13|2026-07-19',
    przyszly: '2026-07-13|2026-07-19',
    setWeek: setWeekMock,
  }),
}))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ confirm: confirmMock }) }))
vi.mock('../components/ui/WeekSelect', () => ({
  WeekSelect: ({ beforeChange }) => (
    <button
      type="button"
      onClick={async () => {
        const allowed = beforeChange ? await beforeChange('2026-07-20|2026-07-26') : true
        if (allowed !== false) setWeekMock('2026-07-20|2026-07-26')
      }}
    >
      Wybór tygodnia
    </button>
  ),
}))
vi.mock('../components/ui/Card', () => ({
  Card: ({ children, className = '', ...props }) => <div className={className} {...props}>{children}</div>,
}))
vi.mock('../components/ui/Hint', () => ({ Hint: ({ children }) => <span>{children}</span> }))
vi.mock('../components/ui/Spinner', () => ({ Spinner: () => <span>Ładowanie</span> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../components/ui/PillSwitch', () => ({
  PillSwitch: ({ value }) => <span>{value ? 'Dostępny' : 'Niedostępny'}</span>,
}))
vi.mock('../components/MojeUrlopy', () => ({ default: () => <div>Panel urlopów</div> }))

import EmployeeAvailability from './EmployeeAvailability'

function mockAvailabilityApi({ existing = [], save } = {}) {
  apiMock.mockImplementation((path, method) => {
    if (path.startsWith('/me/dyspozycje') && !method) return Promise.resolve(existing)
    if (path.startsWith('/me/imprezy')) return Promise.resolve([])
    if (path === '/me/rezerwacje') return Promise.resolve({ dni: [] })
    if (path.startsWith('/me/grafik')) return Promise.resolve({ opublikowany: false })
    if (path === '/me/dyspozycje' && method === 'PUT') return save ? save() : Promise.resolve({ zapisano: 7 })
    return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
  })
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('EmployeeAvailability', () => {
  it('trzyma urlopy w domyślnie zwiniętej sekcji', async () => {
    mockAvailabilityApi()

    render(<EmployeeAvailability />)
    await screen.findAllByText('Dostępny')

    const summary = screen.getByText('Urlopy i nieobecności').closest('summary')
    const details = summary.closest('details')
    const panel = screen.getByText('Panel urlopów')
    expect(details).not.toHaveAttribute('open')
    expect(panel).not.toBeVisible()

    fireEvent.click(summary)

    expect(details).toHaveAttribute('open')
    expect(panel).toBeVisible()
  })

  it('blokuje ponowny zapis, zachowuje układ przy oczekiwaniu i potwierdza wynik lokalnie', async () => {
    let resolveSave
    mockAvailabilityApi({
      save: () => new Promise((resolve) => { resolveSave = resolve }),
    })

    render(<EmployeeAvailability />)
    await screen.findAllByText('Dostępny')

    expect(screen.getByText('Masz niezapisane zmiany.')).toBeInTheDocument()
    const saveButton = screen.getByRole('button', { name: 'Zapisz dyspozycyjność' })
    fireEvent.click(saveButton)

    const pendingButton = await screen.findByRole('button', { name: 'Zapisywanie…' })
    expect(pendingButton).toBeDisabled()
    fireEvent.click(pendingButton)
    expect(apiMock.mock.calls.filter(([path, method]) => path === '/me/dyspozycje' && method === 'PUT')).toHaveLength(1)

    await act(async () => resolveSave({ zapisano: 7 }))

    expect(await screen.findByText(/Zapisano o/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zapisz dyspozycyjność' })).toBeDisabled()
  })

  it('pokazuje błąd obok zapisu i pozwala ponowić bez utraty zmian', async () => {
    let attempts = 0
    mockAvailabilityApi({
      save: () => {
        attempts += 1
        return attempts === 1
          ? Promise.reject(new Error('Brak połączenia.'))
          : Promise.resolve({ zapisano: 7 })
      },
    })

    render(<EmployeeAvailability />)
    await screen.findAllByText('Dostępny')
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz dyspozycyjność' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia.')
    expect(screen.getByText(/Zmiany nadal są na ekranie/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(await screen.findByText(/Zapisano o/)).toBeInTheDocument()
    expect(attempts).toBe(2)
  })

  it('po błędzie wczytania nie pozwala zapisać starego tygodnia i oferuje retry', async () => {
    let loadAttempts = 0
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/me/dyspozycje')) {
        loadAttempts += 1
        return loadAttempts === 1 ? Promise.reject(new Error('Serwer jest niedostępny.')) : Promise.resolve([])
      }
      if (path.startsWith('/me/imprezy')) return Promise.resolve([])
      if (path === '/me/rezerwacje') return Promise.resolve({ dni: [] })
      if (path.startsWith('/me/grafik')) return Promise.resolve({ opublikowany: false })
      return Promise.resolve({})
    })

    render(<EmployeeAvailability />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Serwer jest niedostępny.')
    expect(screen.queryByRole('button', { name: 'Zapisz dyspozycyjność' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj wczytać ponownie' }))

    await screen.findAllByText('Dostępny')
    expect(screen.getByRole('button', { name: 'Zapisz dyspozycyjność' })).toBeEnabled()
  })

  it('ostrzega przed zmianą tygodnia z niezapisanymi danymi', async () => {
    confirmMock.mockResolvedValue(false)
    mockAvailabilityApi()
    render(<EmployeeAvailability />)
    await screen.findAllByText('Dostępny')
    setWeekMock.mockClear()

    fireEvent.click(screen.getByRole('button', { name: 'Wybór tygodnia' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Masz niezapisane zmiany'),
      expect.objectContaining({ confirmText: 'Zmień okres' }),
    ))
    expect(setWeekMock).not.toHaveBeenCalled()
    expect(screen.getByText('Masz niezapisane zmiany.')).toBeInTheDocument()
  })
})
