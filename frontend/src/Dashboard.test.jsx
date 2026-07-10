// @vitest-environment jsdom
import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'

const { apiMock, logoutMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  logoutMock: vi.fn(),
}))

vi.mock('./lib/api', () => ({ api: apiMock }))
vi.mock('./context/AuthContext', () => ({
  useAuth: () => ({ user: { login: 'admin' }, logout: logoutMock }),
}))
vi.mock('./context/BrandingContext', () => ({
  useBranding: () => ({ nazwa_lokalu: 'Lokalo Test' }),
}))
vi.mock('./components/Logo', () => ({ Logo: () => <span>Lokalo</span> }))
vi.mock('./components/PushButton', () => ({ PushButton: () => <button type="button">Powiadomienia</button> }))
vi.mock('./lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('./components/tabs/Pulpit', () => ({ default: () => <div>Treść pulpitu</div> }))

const CONFIG = {
  modul_rezerwacje: true,
  modul_imprezy: true,
  modul_sprzatanie: true,
  modul_rozliczenia: true,
  modul_pos: true,
}

describe('Dashboard', () => {
  afterEach(cleanup)

  beforeEach(() => {
    apiMock.mockReset()
    logoutMock.mockReset()
    apiMock.mockImplementation((path) => {
      if (path === '/lokal/config') return Promise.resolve(CONFIG)
      if (path === '/subskrypcja') return Promise.resolve({ stan: 'aktywna' })
      if (path === '/flota') return Promise.resolve({ enabled: false })
      return Promise.resolve({})
    })
  })

  it('pokazuje tylko bieżące ścieżki rezerwacji i imprez', async () => {
    render(<Dashboard />)

    const goscie = await screen.findByRole('button', { name: 'Goście' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Imprezy' })).toBeInTheDocument())

    fireEvent.click(goscie)
    expect(screen.getByRole('button', { name: 'Rezerwacje stolików' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rezerwacje (ruch)' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Imprezy' }))
    expect(screen.getByRole('button', { name: 'Kalendarz imprez' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zapytania o imprezy' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zadatki' })).not.toBeInTheDocument()
  })

  it('wyłącza fokus w zamkniętym menu mobilnym', () => {
    const { container } = render(<Dashboard />)
    const drawer = container.querySelector('aside[aria-label="Menu administracyjne"]')

    expect(drawer).toHaveAttribute('aria-hidden', 'true')
    expect(drawer).toHaveAttribute('inert')

    fireEvent.click(screen.getByRole('button', { name: 'Otwórz menu' }))

    expect(drawer).toHaveAttribute('aria-hidden', 'false')
    expect(drawer).not.toHaveAttribute('inert')
    expect(screen.getByRole('button', { name: 'Zamknij menu' })).toBeInTheDocument()
  })
})
