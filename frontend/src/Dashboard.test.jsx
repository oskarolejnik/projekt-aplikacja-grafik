// @vitest-environment jsdom
import React from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Dashboard from './Dashboard'
import { registerReservationLeaveGuard } from './lib/reservationLeaveGuard'
import { writeReservationSession } from './lib/reservationSession'

const { apiMock, logoutMock, dashboardState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  logoutMock: vi.fn(),
  dashboardState: { pulpitError: false, pracownicyLoads: 0, reservationUnmounts: 0 },
}))

vi.mock('./lib/api', () => ({ api: apiMock, getApiBase: () => '' }))
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
vi.mock('./components/tabs/Pracownicy', () => {
  dashboardState.pracownicyLoads += 1
  return { default: () => <div>Treść pracowników</div> }
})
vi.mock('./components/tabs/ReservationsWorkspace', () => ({
  default: () => {
    React.useEffect(() => () => { dashboardState.reservationUnmounts += 1 }, [])
    return <div>Workspace rezerwacji</div>
  },
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
    window.history.replaceState(null, '', '/')
    window.sessionStorage.clear()
    apiMock.mockReset()
    logoutMock.mockReset()
    dashboardState.pulpitError = false
    dashboardState.pracownicyLoads = 0
    dashboardState.reservationUnmounts = 0
    apiMock.mockImplementation((path) => {
      if (path === '/lokal/config') return Promise.resolve(CONFIG)
      if (path === '/subskrypcja') return Promise.resolve({ stan: 'aktywna' })
      if (path === '/flota') return Promise.resolve({ enabled: false })
      return Promise.resolve({})
    })
  })

  it('prefetchuje tylko zakładkę wskazaną fokusem, bez przełączania widoku', async () => {
    render(<Dashboard />)

    fireEvent.click(await screen.findByRole('button', { name: 'Zespół' }))
    const pracownicy = screen.getByRole('button', { name: 'Pracownicy' })
    expect(dashboardState.pracownicyLoads).toBe(0)

    fireEvent.focus(pracownicy)

    await waitFor(() => expect(dashboardState.pracownicyLoads).toBe(1))
    expect(screen.queryByText('Treść pracowników')).not.toBeInTheDocument()
    expect(screen.getByText('Treść pulpitu')).toBeInTheDocument()
  })

  it('pokazuje tylko bieżące ścieżki rezerwacji i imprez', async () => {
    render(<Dashboard />)

    const goscie = await screen.findByRole('button', { name: 'Goście' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Imprezy' })).toBeInTheDocument())

    fireEvent.click(goscie)
    expect(screen.getByRole('button', { name: 'Rezerwacje' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Plan sali' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Widok hosta' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rezerwacje stolików' })).not.toBeInTheDocument()
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
    const trigger = screen.getByRole('button', { name: 'Otwórz menu' })

    expect(drawer).toHaveAttribute('aria-hidden', 'true')
    expect(drawer).toHaveAttribute('inert')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    trigger.focus()
    fireEvent.click(trigger)

    expect(drawer).toHaveAttribute('aria-hidden', 'false')
    expect(drawer).not.toHaveAttribute('inert')
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(drawer).toHaveAttribute('role', 'dialog')
    expect(document.body.style.overflow).toBe('hidden')
    expect(screen.getByRole('button', { name: 'Zamknij menu' })).toHaveFocus()

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(drawer).toHaveAttribute('aria-hidden', 'true')
    expect(document.body.style.overflow).toBe('')
    expect(trigger).toHaveFocus()
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

  it('otwiera workspace rezerwacji z bezpośredniego linku i obsługuje powrót', async () => {
    window.history.replaceState({}, '', '/#/rezerwacje/kalendarz?data=2026-07-20')
    render(<Dashboard />)

    expect(await screen.findByText('Workspace rezerwacji')).toBeInTheDocument()

    act(() => {
      window.history.replaceState({ lokaloDashboardTab: 'pulpit' }, '', '/')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    expect(await screen.findByText('Treść pulpitu')).toBeInTheDocument()
    expect(window.location.hash).toBe('')
  })

  it('nie opuszcza workspace bez decyzji o odrzuceniu lokalnego szkicu', async () => {
    window.history.replaceState({}, '', '/#/rezerwacje/sale?sala=1')
    const leaveGuard = vi.fn().mockResolvedValue(false)
    const unregister = registerReservationLeaveGuard(leaveGuard)

    try {
      render(<Dashboard />)
      expect(await screen.findByText('Workspace rezerwacji')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Ustawienia lokalu' }))
      await waitFor(() => expect(leaveGuard).toHaveBeenCalledTimes(1))
      expect(screen.getByText('Workspace rezerwacji')).toBeInTheDocument()
      expect(window.location.hash).toBe('#/rezerwacje/sale?sala=1')

      leaveGuard.mockResolvedValue(true)
      fireEvent.click(screen.getByRole('button', { name: 'Ustawienia lokalu' }))

      expect(await screen.findByText('Ustawienia: lokal')).toBeInTheDocument()
      expect(window.location.hash).toBe('')
    } finally {
      unregister()
    }
  })

  it('chroni lokalny szkic także przy przycisku Wstecz przeglądarki', async () => {
    window.history.replaceState({ lokaloDashboardTab: 'pulpit' }, '', '/')
    window.history.pushState({ lokaloDashboardTab: 'rezerwacje' }, '', '/#/rezerwacje/sale?sala=1')
    const leaveGuard = vi.fn().mockResolvedValue(false)
    const unregister = registerReservationLeaveGuard(leaveGuard)

    try {
      render(<Dashboard />)
      expect(await screen.findByText('Workspace rezerwacji')).toBeInTheDocument()

      act(() => window.history.back())
      await waitFor(() => expect(leaveGuard).toHaveBeenCalledTimes(1))
      await waitFor(() => expect(window.location.hash).toBe('#/rezerwacje/sale?sala=1'))
      expect(screen.getByText('Workspace rezerwacji')).toBeInTheDocument()
      expect(dashboardState.reservationUnmounts).toBe(0)

      leaveGuard.mockResolvedValue(true)
      act(() => window.history.back())
      await waitFor(() => expect(leaveGuard).toHaveBeenCalledTimes(2))
      await waitFor(() => expect(window.location.hash).toBe(''))
      expect(await screen.findByText('Treść pulpitu')).toBeInTheDocument()
    } finally {
      unregister()
    }
  })

  it('po ponownym wejściu przywraca ostatni bezpieczny kontekst operatora', async () => {
    writeReservationSession({ login: 'admin' }, {
      route: { view: 'calendar', date: '2026-07-22', mode: 'day' },
    })
    render(<Dashboard />)

    fireEvent.click(await screen.findByRole('button', { name: 'Goście' }))
    fireEvent.click(screen.getByRole('button', { name: 'Rezerwacje' }))

    expect(await screen.findByText('Workspace rezerwacji')).toBeInTheDocument()
    expect(window.location.hash).toBe('#/rezerwacje/kalendarz?data=2026-07-22&zakres=day')
    expect(window.history.state).toMatchObject({
      lokaloReservationActor: expect.any(String),
      lokaloReservationPrivacyEpoch: expect.any(String),
    })
  })

  it('nie montuje deep linku rezerwacji, gdy moduł lokalu jest wyłączony', async () => {
    window.history.replaceState({}, '', '/#/rezerwacje/baza?od=2026-07-01&do=2026-07-31')
    apiMock.mockImplementation((path) => {
      if (path === '/lokal/config') return Promise.resolve({ ...CONFIG, modul_rezerwacje: false })
      if (path === '/subskrypcja') return Promise.resolve({ stan: 'aktywna' })
      if (path === '/flota') return Promise.resolve({ enabled: false })
      return Promise.resolve({})
    })

    render(<Dashboard />)

    expect(await screen.findByText('Treść pulpitu')).toBeInTheDocument()
    await waitFor(() => expect(window.location.hash).toBe(''))
    expect(screen.queryByText('Workspace rezerwacji')).not.toBeInTheDocument()
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
