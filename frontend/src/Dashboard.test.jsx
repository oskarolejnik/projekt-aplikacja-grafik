// @vitest-environment jsdom
import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'

const { apiMock, logoutMock, dashboardState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  logoutMock: vi.fn(),
  dashboardState: { pulpitError: false },
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
vi.mock('./components/tabs/Pulpit', () => ({
  default: () => {
    if (dashboardState.pulpitError) throw new Error('pulpit chunk unavailable')
    return <div>Treść pulpitu</div>
  },
}))
vi.mock('./components/tabs/Ustawienia', () => ({
  default: ({ initialSection }) => <div>Ustawienia: {initialSection}</div>,
}))

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
    dashboardState.pulpitError = false
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

  it('grupuje plan, dyspozycje i edycję w jednym wejściu Grafik pracy', async () => {
    render(<Dashboard />)

    const grafik = await screen.findByRole('button', { name: 'Grafik' })
    fireEvent.click(grafik)

    expect(screen.getByRole('button', { name: 'Grafik pracy' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Interaktywny grafik' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Wymagania (plan)' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dyspozycyjność' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Giełda zmian' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Raport godzin' })).toBeInTheDocument()
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

  it('prowadzi z alertu płatności bezpośrednio do planu', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/lokal/config') return Promise.resolve(CONFIG)
      if (path === '/subskrypcja') return Promise.resolve({ stan: 'grace', data_grace: '2026-07-15' })
      if (path === '/flota') return Promise.resolve({ enabled: false })
      return Promise.resolve({})
    })

    render(<Dashboard />)

    fireEvent.click(await screen.findByRole('button', { name: 'Przejdź do subskrypcji' }))
    expect(await screen.findByText('Ustawienia: plan')).toBeInTheDocument()
  })

  it('ponawia ładowanie uszkodzonej zakładki bez przeładowania panelu', async () => {
    const consoleMock = vi.spyOn(console, 'error').mockImplementation(() => {})
    const preventError = (event) => event.preventDefault()
    window.addEventListener('error', preventError)
    dashboardState.pulpitError = true

    try {
      render(<Dashboard />)

      expect(await screen.findByRole('alert')).toHaveTextContent('Nie udało się wczytać widoku')
      dashboardState.pulpitError = false
      fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))
      expect(await screen.findByText('Treść pulpitu')).toBeInTheDocument()
    } finally {
      window.removeEventListener('error', preventError)
      consoleMock.mockRestore()
    }
  })
})
