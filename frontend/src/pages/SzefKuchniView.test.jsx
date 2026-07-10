// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'

const { logoutMock } = vi.hoisted(() => ({ logoutMock: vi.fn() }))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { imie: 'Marta' }, logout: logoutMock }),
}))
vi.mock('../context/BrandingContext', () => ({ useBranding: () => ({ nazwa_lokalu: 'Lokalo Test' }) }))
vi.mock('../components/Logo', () => ({ Logo: () => <span>Lokalo</span> }))
vi.mock('../components/PushButton', () => ({ PushButton: () => <button type="button">Powiadomienia</button> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../components/tabs/StolyLive', () => ({ default: () => <div>Widok stołów</div> }))
vi.mock('../components/tabs/Rezerwacje', () => ({ default: () => <div>Widok rezerwacji</div> }))
vi.mock('./SzefKuchniGrafik', () => ({ default: () => <div>Widok grafiku kuchni</div> }))

import SzefKuchniView from './SzefKuchniView'

describe('SzefKuchniView shell', () => {
  afterEach(() => {
    cleanup()
    logoutMock.mockReset()
  })

  it('ma semantyczną nawigację, aktywny stan i cele dotykowe 44 px', () => {
    render(<SzefKuchniView />)

    const nav = screen.getByRole('navigation', { name: 'Widoki szefa kuchni' })
    const grafik = within(nav).getByRole('button', { name: 'Grafik' })
    const stoly = within(nav).getByRole('button', { name: 'Stoły' })
    const logout = screen.getByRole('button', { name: 'Wyloguj' })

    expect(grafik).toHaveAttribute('aria-current', 'page')
    expect(grafik).toHaveClass('min-h-11')
    expect(logout).toHaveClass('min-h-11', 'min-w-11')

    fireEvent.click(stoly)

    expect(stoly).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Widok stołów')).toBeInTheDocument()
  })
})
