// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, logoutMock, userState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  logoutMock: vi.fn(),
  userState: { current: { rola: 'employee', imie: 'Ania', login: 'ania' } },
}))

vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: userState.current, logout: logoutMock }),
}))
vi.mock('../context/DataContext', () => ({ useData: () => ({ biezacy: '2026-07-06|2026-07-12' }) }))
vi.mock('../context/BrandingContext', () => ({ useBranding: () => ({ nazwa_lokalu: 'Testowy lokal' }) }))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../components/Logo', () => ({ Logo: () => <span>Logo</span> }))
vi.mock('../components/PushButton', () => ({ PushButton: () => <button type="button">Push</button> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('./EmployeeAvailability', () => ({ default: () => <div>Dyspozycyjność pracownika</div> }))
vi.mock('./EmployeeSchedule', () => ({ default: () => <div>Grafik pracownika</div> }))
vi.mock('./EmployeeHours', () => ({ default: () => <div>Godziny pracownika</div> }))
vi.mock('./EmployeeGielda', () => ({ default: () => <div>Giełda pracownika</div> }))
vi.mock('./EmployeeOgloszenia', () => ({ default: () => <div>Ogłoszenia pracownika</div> }))
vi.mock('../components/tabs/Rezerwacje', () => ({ default: () => <div>Rezerwacje pracownika</div> }))
vi.mock('../components/tabs/KuchniaImprezy', () => ({ default: () => <div>Imprezy pracownika</div> }))
vi.mock('../components/tabs/TechSprzatanie', () => ({ default: () => <div data-testid="sprzatanie-view">Sprzątanie</div> }))
vi.mock('../components/tabs/TechZamowienia', () => ({ default: () => <div>Zamówienia</div> }))

import EmployeeArea from './EmployeeArea'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  userState.current = { rola: 'employee', imie: 'Ania', login: 'ania' }
})

describe('EmployeeArea', () => {
  it('stawia Grafik na pierwszym miejscu, zachowując Rezerwacje i Imprezy', async () => {
    apiMock.mockResolvedValue({ nieprzeczytane: 2, opublikowany: false })
    render(<EmployeeArea />)

    expect(screen.getByText('Grafik pracownika')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Widoki pracownika' })
    expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Grafik', 'Godziny', 'Dyspo', 'Giełda', 'Rezerwacje', 'Imprezy',
    ])
    expect(within(nav).getByRole('button', { name: 'Grafik' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('button', { name: 'Rezerwacje' })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Imprezy' })).toBeInTheDocument()
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
    expect(within(nav).queryByRole('button', { name: 'Dyspo' })).not.toBeInTheDocument()
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
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/me/ogloszenia'))
    expect(apiMock).not.toHaveBeenCalledWith(expect.stringContaining('/me/grafik'))
  })
})
