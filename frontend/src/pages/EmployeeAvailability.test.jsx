// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, setWeekMock, toastMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  setWeekMock: vi.fn(),
  toastMock: vi.fn(),
}))

vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../context/DataContext', () => ({
  useData: () => ({
    week: '2026-07-13|2026-07-19',
    przyszly: '2026-07-13|2026-07-19',
    setWeek: setWeekMock,
  }),
}))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../components/ui/WeekSelect', () => ({ WeekSelect: () => <div>Wybór tygodnia</div> }))
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

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('EmployeeAvailability', () => {
  it('trzyma urlopy w domyślnie zwiniętej sekcji', async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/me/dyspozycje')) return Promise.resolve([])
      if (path.startsWith('/me/imprezy')) return Promise.resolve([])
      if (path === '/me/rezerwacje') return Promise.resolve({ dni: [] })
      if (path.startsWith('/me/grafik')) return Promise.resolve({ opublikowany: false })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

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
})
