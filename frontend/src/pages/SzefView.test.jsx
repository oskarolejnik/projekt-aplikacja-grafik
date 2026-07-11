// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { authState, logoutMock } = vi.hoisted(() => ({
  authState: {
    permissions: ['grafik.podglad', 'raporty.podglad'],
    ready: true,
    user: { login: 'manager', imie: 'Marta', rola: 'szef' },
  },
  logoutMock: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: authState.user,
    logout: logoutMock,
    uprawnieniaReady: authState.ready,
    can: (permission) => authState.permissions.includes(permission),
  }),
}))
vi.mock('../context/BrandingContext', () => ({ useBranding: () => ({ nazwa_lokalu: 'Lokalo Test' }) }))
vi.mock('../components/Logo', () => ({ Logo: () => <span>Logo</span> }))
vi.mock('../components/PushButton', () => ({ PushButton: () => <button type="button">Powiadomienia</button> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../components/tabs/SzefGrafik', () => ({ default: () => <div>Widok grafiku</div> }))
vi.mock('../components/tabs/StolyLive', () => ({ default: () => <div>Widok stołów</div> }))
vi.mock('../components/tabs/Zeszyt', () => ({ default: () => <div>Widok zeszytu</div> }))
vi.mock('../components/tabs/RaportGodzin', () => ({ default: () => <div>Widok godzin</div> }))
vi.mock('../components/tabs/SzefImprezy', () => ({ default: () => <div>Widok imprez</div> }))
vi.mock('../components/tabs/Rezerwacje', () => ({ default: () => <div>Widok rezerwacji</div> }))
vi.mock('../components/tabs/RezerwacjeStolik', () => ({ default: () => <div>Operacyjne rezerwacje dnia</div> }))
vi.mock('../components/tabs/WidokHosta', () => ({ default: () => <div>Operacyjny widok hosta</div> }))

import SzefView from './SzefView'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  authState.permissions = ['grafik.podglad', 'raporty.podglad']
  authState.ready = true
  authState.user = { login: 'manager', imie: 'Marta', rola: 'szef' }
})

describe('SzefView permissions', () => {
  it('otwiera Grafik i montuje wyłącznie aktywny, dozwolony widok', () => {
    render(<SzefView />)

    const nav = screen.getByRole('navigation', { name: 'Widoki szefa' })
    expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Grafik', 'Stoły', 'Godziny',
    ])
    expect(within(nav).getByRole('button', { name: 'Grafik' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Widok grafiku')).toBeInTheDocument()
    expect(screen.queryByText('Widok godzin')).not.toBeInTheDocument()
    expect(screen.queryByText('Widok zeszytu')).not.toBeInTheDocument()

    fireEvent.click(within(nav).getByRole('button', { name: 'Godziny' }))
    expect(screen.getByText('Widok godzin')).toBeInTheDocument()
    expect(screen.queryByText('Widok grafiku')).not.toBeInTheDocument()
  })

  it('nie montuje Grafiku, gdy konto ma wyłącznie prawo do raportu', async () => {
    authState.permissions = ['raporty.podglad']
    render(<SzefView />)

    await waitFor(() => expect(screen.getByText('Widok godzin')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Grafik' })).not.toBeInTheDocument()
    expect(screen.queryByText('Widok grafiku')).not.toBeInTheDocument()
  })

  it('daje Recepcji / Hostowi prosty workspace z właściwym widokiem domyślnym', async () => {
    authState.user = { login: 'recepcja', imie: 'Ola', rola: 'szef', preset: 'recepcja_host' }
    authState.permissions = ['rezerwacje.operacje', 'rezerwacje.host', 'rezerwacje.dane_kontaktowe']

    render(<SzefView />)

    expect(screen.getByText('Recepcja / Host · Ola')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Widoki recepcji' })
    expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Rezerwacje dzisiaj', 'Host',
    ])
    await waitFor(() => expect(screen.getByText('Operacyjne rezerwacje dnia')).toBeInTheDocument())
    expect(within(nav).getByRole('button', { name: 'Rezerwacje dzisiaj' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('button', { name: 'Grafik' })).not.toBeInTheDocument()

    fireEvent.click(within(nav).getByRole('button', { name: 'Host' }))
    expect(screen.getByText('Operacyjny widok hosta')).toBeInTheDocument()
    expect(screen.queryByText('Operacyjne rezerwacje dnia')).not.toBeInTheDocument()
  })

  it('po cofnięciu presetu wraca do etykiety managera na podstawie bieżących praw', async () => {
    authState.user = { login: 'recepcja', imie: 'Ola', rola: 'szef', preset: 'recepcja_host' }
    authState.permissions = ['rezerwacje.operacje', 'rezerwacje.host']
    const { rerender } = render(<SzefView />)
    expect(screen.getByText('Recepcja / Host · Ola')).toBeInTheDocument()

    authState.permissions = ['grafik.podglad', 'raporty.podglad']
    rerender(<SzefView />)

    expect(await screen.findByText('Panel szefa · Ola')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Widoki szefa' })).toBeInTheDocument()
    expect(screen.queryByText('Recepcja / Host · Ola')).not.toBeInTheDocument()
  })

  it('czeka na uprawnienia i pokazuje spokojny stan pusty bez montowania zakładek', () => {
    authState.ready = false
    authState.permissions = []
    const { rerender } = render(<SzefView />)

    expect(screen.getByRole('status', { name: 'Wczytywanie dostępu' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Widoki szefa' })).not.toBeInTheDocument()

    authState.ready = true
    rerender(<SzefView />)
    expect(screen.getByText('Brak przydzielonych widoków')).toBeInTheDocument()
    expect(screen.queryByText(/Widok /)).not.toBeInTheDocument()
  })
})
