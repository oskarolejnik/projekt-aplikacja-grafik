// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, confirmMock, logoutMock, userState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  logoutMock: vi.fn(),
  userState: { current: { rola: 'employee', imie: 'Ania', login: 'ania' } },
}))

vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: userState.current, logout: logoutMock }),
}))
vi.mock('../context/DataContext', () => ({ useData: () => ({ biezacy: '2026-07-06|2026-07-12' }) }))
vi.mock('../context/BrandingContext', () => ({ useBranding: () => ({ nazwa_lokalu: 'Testowy lokal' }) }))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: vi.fn(), confirm: confirmMock }) }))
vi.mock('../components/Logo', () => ({ Logo: () => <span>Logo</span> }))
vi.mock('../components/PushButton', () => ({ PushButton: () => <button type="button">Push</button> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('./EmployeeAvailability', () => ({
  default: ({ onDirtyChange }) => (
    <div>
      Dyspozycyjność pracownika
      <button type="button" onClick={() => onDirtyChange(true)}>Wprowadź niezapisane zmiany</button>
    </div>
  ),
}))
vi.mock('./EmployeeSchedule', () => ({ default: () => <div>Grafik pracownika</div> }))
vi.mock('./EmployeeHours', () => ({ default: () => <div>Godziny pracownika</div> }))
vi.mock('./EmployeeGielda', () => ({ default: () => <div>Giełda pracownika</div> }))
vi.mock('./EmployeeOgloszenia', () => ({ default: () => <div>Ogłoszenia pracownika</div> }))
vi.mock('../components/tabs/Rezerwacje', () => ({ default: () => <div>Rezerwacje pracownika</div> }))
vi.mock('../components/tabs/KuchniaImprezy', () => ({ default: () => <div>Imprezy pracownika</div> }))
vi.mock('../components/tabs/TechSprzatanie', () => ({ default: () => <div data-testid="sprzatanie-view">Sprzątanie</div> }))
vi.mock('../components/tabs/TechZamowienia', () => ({ default: () => <div>Zamówienia</div> }))

import EmployeeArea from './EmployeeArea'

const originalMatchMedia = window.matchMedia

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  confirmMock.mockResolvedValue(true)
  userState.current = { rola: 'employee', imie: 'Ania', login: 'ania' }
  Object.defineProperty(window, 'matchMedia', { configurable: true, writable: true, value: originalMatchMedia })
})

describe('EmployeeArea', () => {
  it('stawia Grafik na pierwszym miejscu, zachowując Rezerwacje i Imprezy', async () => {
    apiMock.mockResolvedValue({ nieprzeczytane: 2, opublikowany: false })
    render(<EmployeeArea />)

    expect(screen.getByText('Grafik pracownika')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Widoki pracownika' })
    expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Grafik', 'Godziny', 'Dyspozycyjność', 'Giełda', 'Rezerwacje', 'Imprezy',
    ])
    expect(within(nav).getByRole('button', { name: 'Grafik' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('button', { name: 'Rezerwacje' })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Imprezy' })).toBeInTheDocument()

    const mobileNav = screen.getByRole('navigation', { name: 'Główna nawigacja mobilna' })
    expect(within(mobileNav).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Grafik', 'Godziny', 'Dyspo', 'Więcej',
    ])
    expect(within(mobileNav).getByRole('button', { name: 'Grafik' })).toHaveAttribute('aria-current', 'page')
  })

  it('udostępnia pozostałe widoki w mobilnym arkuszu i oznacza aktywne Więcej', () => {
    apiMock.mockResolvedValue({ nieprzeczytane: 0, opublikowany: false })
    render(<EmployeeArea />)

    const mobileNav = screen.getByRole('navigation', { name: 'Główna nawigacja mobilna' })
    const wiecej = within(mobileNav).getByRole('button', { name: 'Więcej' })
    fireEvent.click(wiecej)

    const dialog = screen.getByRole('dialog', { name: 'Więcej widoków' })
    expect(within(dialog).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '', 'Giełda', 'Rezerwacje', 'Imprezy',
    ])
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rezerwacje' }))

    expect(screen.getByText('Rezerwacje pracownika')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Więcej widoków' })).not.toBeInTheDocument()
    expect(wiecej).toHaveAttribute('aria-current', 'page')
  })

  it('nie gubi dyspozycyjności przy przypadkowej zmianie widoku', async () => {
    apiMock.mockResolvedValue({ nieprzeczytane: 0, opublikowany: false })
    confirmMock.mockResolvedValue(false)
    render(<EmployeeArea />)
    const nav = screen.getByRole('navigation', { name: 'Widoki pracownika' })

    fireEvent.click(within(nav).getByRole('button', { name: 'Dyspozycyjność' }))
    fireEvent.click(screen.getByRole('button', { name: 'Wprowadź niezapisane zmiany' }))
    fireEvent.click(within(nav).getByRole('button', { name: 'Grafik' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Masz niezapisane zmiany'),
      expect.objectContaining({ confirmText: 'Opuść bez zapisu' }),
    ))
    expect(screen.getByText('Dyspozycyjność pracownika')).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Dyspozycyjność' })).toHaveAttribute('aria-current', 'page')

    confirmMock.mockResolvedValue(true)
    fireEvent.click(within(nav).getByRole('button', { name: 'Grafik' }))
    expect(await screen.findByText('Grafik pracownika')).toBeInTheDocument()
  })

  it('zamyka mobilny arkusz przez Escape i oddaje fokus do Więcej', () => {
    apiMock.mockResolvedValue({ nieprzeczytane: 0, opublikowany: false })
    render(<EmployeeArea />)

    const wiecej = within(screen.getByRole('navigation', { name: 'Główna nawigacja mobilna' }))
      .getByRole('button', { name: 'Więcej' })
    fireEvent.click(wiecej)
    expect(screen.getByRole('dialog', { name: 'Więcej widoków' })).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(screen.queryByRole('dialog', { name: 'Więcej widoków' })).not.toBeInTheDocument()
    expect(wiecej).toHaveFocus()
  })

  it('zamyka mobilny arkusz i zwalnia przewijanie po wejściu w breakpoint desktopowy', () => {
    let onBreakpoint
    const removeEventListener = vi.fn()
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn(() => ({
        matches: false,
        media: '(min-width: 768px)',
        addEventListener: vi.fn((event, handler) => {
          if (event === 'change') onBreakpoint = handler
        }),
        removeEventListener,
      })),
    })
    apiMock.mockResolvedValue({ nieprzeczytane: 0, opublikowany: false })
    render(<EmployeeArea />)

    const wiecej = within(screen.getByRole('navigation', { name: 'Główna nawigacja mobilna' }))
      .getByRole('button', { name: 'Więcej' })
    fireEvent.click(wiecej)
    expect(screen.getByRole('dialog', { name: 'Więcej widoków' })).toBeInTheDocument()
    expect(document.body.style.overflow).toBe('hidden')

    act(() => onBreakpoint({ matches: true }))

    expect(screen.queryByRole('dialog', { name: 'Więcej widoków' })).not.toBeInTheDocument()
    expect(document.body.style.overflow).toBe('')
    expect(wiecej).toHaveFocus()
  })

  it('otwiera ogłoszenia z dzwonka zamiast zajmować slot głównej nawigacji', async () => {
    apiMock.mockResolvedValue({ nieprzeczytane: 2, opublikowany: false })
    render(<EmployeeArea />)

    const dzwonek = await screen.findByRole('button', { name: 'Ogłoszenia, 2 nieprzeczytane' })
    fireEvent.click(dzwonek)

    expect(screen.getByText('Ogłoszenia pracownika')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Widoki pracownika' })).not.toHaveTextContent('Ogłoszenia')
  })

  it('zachowuje kolejność uproszczonego widoku kuchni', () => {
    userState.current = { rola: 'kuchnia', imie: 'Kuba', login: 'kuba' }
    apiMock.mockResolvedValue({ nieprzeczytane: 0, opublikowany: false })
    render(<EmployeeArea />)

    const nav = screen.getByRole('navigation', { name: 'Widoki pracownika' })
    expect(screen.getByText('Grafik pracownika')).toBeInTheDocument()
    expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Grafik', 'Godziny', 'Giełda', 'Rezerwacje', 'Imprezy',
    ])
    expect(within(nav).queryByRole('button', { name: 'Dyspozycyjność' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('navigation', { name: 'Główna nawigacja mobilna' }))
      .getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Grafik', 'Godziny', 'Giełda', 'Więcej',
    ])
  })

  it('stawia Sprzątanie na początku widoku technicznego i nie pobiera grafiku', async () => {
    userState.current = { rola: 'employee', dzial: 'techniczny', sprzataczka: true, imie: 'Ola', login: 'ola' }
    apiMock.mockResolvedValue({ nieprzeczytane: 0, opublikowany: false })
    render(<EmployeeArea />)

    const nav = screen.getByRole('navigation', { name: 'Widoki pracownika' })
    expect(screen.getByTestId('sprzatanie-view')).toBeInTheDocument()
    expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Sprzątanie', 'Zamówienia', 'Godziny',
    ])
    expect(within(nav).getByRole('button', { name: 'Sprzątanie' })).toHaveAttribute('aria-current', 'page')
    expect(within(screen.getByRole('navigation', { name: 'Główna nawigacja mobilna' }))
      .getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Sprzątanie', 'Zamówienia', 'Godziny',
    ])
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/me/ogloszenia'))
    expect(apiMock).not.toHaveBeenCalledWith(expect.stringContaining('/me/grafik'))
  })
})
