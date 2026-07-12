// @vitest-environment jsdom
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const auth = vi.hoisted(() => ({
  user: { id: 17, login: 'recepcja' },
  isAdmin: false,
  permissions: new Set(),
}))
const { apiMock, confirmMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({
  api: apiMock,
  getApiBase: () => '',
}))

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: auth.user,
    isAdmin: auth.isAdmin,
    can: (permission) => auth.permissions.has(permission),
  }),
}))

vi.mock('../../lib/icons', () => ({
  Icon: ({ name }) => <span aria-hidden="true">{name}</span>,
}))

vi.mock('../ui/Toast', () => ({
  useToast: () => ({ confirm: confirmMock }),
}))

vi.mock('./RezerwacjeStolik', () => ({
  default: ({ date, reservationId, suspendReservationDialog, onGuestProfileOpen }) => {
    const [note, setNote] = useState('')
    return (
      <div>
        <span data-testid="today-date">{date}</span>
        <span data-testid="today-reservation">{reservationId ?? 'brak'}</span>
        <span data-testid="today-suspended">{String(Boolean(suspendReservationDialog))}</span>
        <label>
          Notatka dnia
          <input value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        {reservationId && !suspendReservationDialog ? (
          <button type="button" onClick={() => onGuestProfileOpen?.(reservationId)}>Profil gościa</button>
        ) : null}
      </div>
    )
  },
}))

vi.mock('./ReservationsCalendar', () => ({
  default: ({ date, mode, status, active }) => (
    <div>
      <span data-testid="calendar-date">{date}</span>
      <span data-testid="calendar-mode">{mode}</span>
      <span data-testid="calendar-status">{status || 'wszystkie'}</span>
      <span data-testid="calendar-active">{String(active)}</span>
    </div>
  ),
}))

vi.mock('./ReservationsDatabase', () => ({
  default: ({ active, onOpenReservation }) => (
    <div>
      <span data-testid="database-active">{String(active)}</span>
      <button
        type="button"
        onClick={() => onOpenReservation({ id: 42, data: '2026-08-21' })}
      >
        Otwórz rezerwację Kowalskiej
      </button>
    </div>
  ),
}))

vi.mock('./WidokHosta', () => ({
  default: ({ date, active }) => (
    <div>
      Widok hosta {date} {String(active)}
    </div>
  ),
}))

vi.mock('./GuestProfileDialog', () => ({
  default: ({ reservationId, onClose, onDirtyChange }) => (
    <div role="dialog" aria-label="Karta gościa">
      Profil rezerwacji {reservationId}
      <button type="button" onClick={() => onDirtyChange?.(true)}>Zmień profil testowo</button>
      <button type="button" onClick={onClose}>Wróć do rezerwacji</button>
    </div>
  ),
}))

import ReservationsWorkspace from './ReservationsWorkspace'
import { purgeReservationPrivacy } from '../../lib/reservationPrivacy'
import { writeReservationSession } from '../../lib/reservationSession'

const ALL_PERMISSIONS = [
  'rezerwacje.operacje',
  'rezerwacje.host',
  'rezerwacje.dane_kontaktowe',
]

function setPermissions(...permissions) {
  auth.permissions = new Set(permissions)
}

function setHash(hash) {
  window.history.replaceState({}, '', hash)
}

beforeEach(() => {
  auth.user = { id: 17, login: 'recepcja' }
  auth.isAdmin = false
  setPermissions(...ALL_PERMISSIONS)
  apiMock.mockReset()
  confirmMock.mockReset()
  confirmMock.mockResolvedValue(true)
  apiMock.mockResolvedValue({ id: 42, data: '2026-08-21' })
  window.localStorage.clear()
  window.sessionStorage.clear()
  setHash('#/rezerwacje/dzisiaj?data=2026-08-17')
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  window.sessionStorage.clear()
  window.history.replaceState({}, '', '/')
})

describe('ReservationsWorkspace', () => {
  it('udostępnia administratorowi wszystkie widoki niezależnie od listy uprawnień', () => {
    auth.isAdmin = true
    setPermissions()

    render(<ReservationsWorkspace />)

    expect(screen.getByRole('button', { name: /Dzisiaj/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Kalendarz/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Baza/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Host/ })).toBeInTheDocument()
  })

  it('wyprowadza widoki z granularnych uprawnień i ukrywa Bazę bez danych kontaktowych', () => {
    setPermissions('rezerwacje.operacje')

    render(<ReservationsWorkspace />)

    expect(screen.getByRole('button', { name: /Dzisiaj/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Kalendarz/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Baza/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Host/ })).not.toBeInTheDocument()
  })

  it('normalizuje niedozwolony deep link konta host-only bez montowania PII', async () => {
    setPermissions('rezerwacje.host')
    setHash('#/rezerwacje/baza?od=2026-07-01&do=2026-07-31&rezerwacja=42')

    render(<ReservationsWorkspace />)

    expect(screen.queryByRole('button', { name: /Dzisiaj/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Baza/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Host/ })).toHaveAttribute('aria-current', 'page')
    await waitFor(() => expect(window.location.hash).toContain('#/rezerwacje/host?data='))
    expect(window.location.hash).not.toContain('rezerwacja=42')
  })

  it('natychmiast odmontowuje Bazę i czyści zaznaczenie po odebraniu kontaktów', async () => {
    setHash('#/rezerwacje/baza?od=2026-07-01&do=2026-07-31')
    const { rerender } = render(<ReservationsWorkspace />)
    expect(await screen.findByTestId('database-active')).toHaveTextContent('true')

    setPermissions('rezerwacje.operacje', 'rezerwacje.host')
    rerender(<ReservationsWorkspace />)

    expect(screen.queryByRole('button', { name: /Baza/ })).not.toBeInTheDocument()
    expect(screen.queryByTestId('database-active')).not.toBeInTheDocument()
    await waitFor(() => expect(window.location.hash).toContain('/dzisiaj'))
  })

  it('odnajduje dzień rezerwacji z bezpośredniego linku zawierającego samo ID', async () => {
    setHash('#/rezerwacje/dzisiaj?data=2026-08-17&rezerwacja=42')

    render(<ReservationsWorkspace />)

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje-stolik/42', 'GET', null, expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    await waitFor(() => expect(screen.getByTestId('today-date')).toHaveTextContent('2026-08-21'))
    expect(screen.getByTestId('today-reservation')).toHaveTextContent('42')
    expect(window.location.hash).toBe('#/rezerwacje/dzisiaj?data=2026-08-21&rezerwacja=42')
  })

  it('odrzuca wpis historii należący do innego operatora przed pobraniem PII', async () => {
    window.history.replaceState(
      { lokaloReservationActor: 'poprzedni-lokal:operator-99' },
      '',
      '/#/rezerwacje/dzisiaj?data=2026-08-17&rezerwacja=42',
    )

    render(<ReservationsWorkspace />)

    await waitFor(() => expect(window.history.state?.lokaloReservationActor).not.toBe('poprzedni-lokal:operator-99'))
    expect(apiMock).not.toHaveBeenCalled()
    expect(screen.getByTestId('today-reservation')).toHaveTextContent('brak')
    expect(window.location.hash).not.toContain('rezerwacja=42')
  })

  it('zachowuje czytelny komunikat, gdy rekord z deep linku już nie istnieje', async () => {
    const missing = new Error('Brak rezerwacji.')
    missing.status = 404
    apiMock.mockRejectedValueOnce(missing)
    setHash('#/rezerwacje/dzisiaj?data=2026-08-17&rezerwacja=404')

    render(<ReservationsWorkspace />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak rezerwacji.')
    expect(screen.getByRole('button', { name: 'Zamknij' })).toBeInTheDocument()
    expect(window.location.hash).not.toContain('rezerwacja=404')
  })

  it('po Back ponownie weryfikuje datę rekordu zamiast ufać staremu cache', async () => {
    setHash('#/rezerwacje/dzisiaj?data=2026-08-17&rezerwacja=42')
    render(<ReservationsWorkspace />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByTestId('today-reservation')).toHaveTextContent('42'))
    const state = window.history.state

    act(() => {
      window.history.replaceState(state, '', '/#/rezerwacje/dzisiaj?data=2026-08-21')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await waitFor(() => expect(screen.getByTestId('today-reservation')).toHaveTextContent('brak'))

    act(() => {
      window.history.replaceState(state, '', '/#/rezerwacje/dzisiaj?data=2026-08-21&rezerwacja=42')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
  })

  it('przywraca scroll po doładowaniu dłuższej zawartości', async () => {
    let resize
    const originalResizeObserver = globalThis.ResizeObserver
    globalThis.ResizeObserver = class {
      constructor(callback) { resize = callback }
      observe() {}
      disconnect() {}
    }
    writeReservationSession(auth.user, {
      route: { view: 'today', date: '2026-08-17' },
      scroll: { today: 420 },
    })
    setHash('')
    let contentHeight = 100

    try {
      const { container } = render(
        <main
          className="overflow-y-auto"
          ref={(node) => {
            if (!node || Object.getOwnPropertyDescriptor(node, 'scrollHeight')) return
            Object.defineProperty(node, 'clientHeight', { configurable: true, get: () => 100 })
            Object.defineProperty(node, 'scrollHeight', { configurable: true, get: () => contentHeight })
          }}
        >
          <ReservationsWorkspace />
        </main>,
      )
      const main = container.querySelector('main')
      expect(main.scrollTop).toBe(0)

      contentHeight = 700
      act(() => resize())

      expect(main.scrollTop).toBe(420)
    } finally {
      globalThis.ResizeObserver = originalResizeObserver
    }
  })

  it('otwiera bezpośredni link do kalendarza wraz z kontekstem', async () => {
    setHash('#/rezerwacje/kalendarz?data=2026-08-17&zakres=day&status=potwierdzona')

    render(<ReservationsWorkspace />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Kalendarz/ })).toHaveAttribute('aria-current', 'page')
    })
    expect(screen.getByTestId('calendar-date')).toHaveTextContent('2026-08-17')
    expect(screen.getByTestId('calendar-mode')).toHaveTextContent('day')
    expect(screen.getByTestId('calendar-status')).toHaveTextContent('potwierdzona')
    expect(screen.getByTestId('calendar-active')).toHaveTextContent('true')
  })

  it('przełącza widok przez pushState i zapisuje kanoniczny hash', async () => {
    const pushState = vi.spyOn(window.history, 'pushState')
    render(<ReservationsWorkspace />)

    fireEvent.click(screen.getByRole('button', { name: /Kalendarz/ }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Kalendarz/ })).toHaveAttribute('aria-current', 'page')
    })
    expect(pushState).toHaveBeenCalled()
    expect(window.location.hash).toBe('#/rezerwacje/kalendarz?data=2026-08-17')
  })

  it('odtwarza poprzedni widok po zdarzeniu Back', async () => {
    render(<ReservationsWorkspace />)
    fireEvent.click(screen.getByRole('button', { name: /Kalendarz/ }))
    await waitFor(() => expect(window.location.hash).toContain('/kalendarz'))

    act(() => {
      window.history.replaceState({}, '', '#/rezerwacje/dzisiaj?data=2026-08-17')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Dzisiaj/ })).toHaveAttribute('aria-current', 'page')
    })
    expect(screen.getByTestId('today-date')).toHaveTextContent('2026-08-17')
  })

  it('otwiera rekord z Bazy w Dzisiaj i zachowuje stan zamontowanego widoku', async () => {
    render(<ReservationsWorkspace />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Notatka dnia' }), {
      target: { value: 'Gość prosi o stolik przy oknie' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Baza/ }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Baza/ })).toHaveAttribute('aria-current', 'page')
    })
    expect(screen.getByTestId('database-active')).toHaveTextContent('true')

    fireEvent.click(screen.getByRole('button', { name: 'Otwórz rezerwację Kowalskiej' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Dzisiaj/ })).toHaveAttribute('aria-current', 'page')
    })
    expect(screen.getByTestId('today-date')).toHaveTextContent('2026-08-21')
    expect(screen.getByTestId('today-reservation')).toHaveTextContent('42')
    expect(screen.getByRole('textbox', { name: 'Notatka dnia' })).toHaveValue(
      'Gość prosi o stolik przy oknie',
    )
    expect(window.location.hash).toBe('#/rezerwacje/dzisiaj?data=2026-08-21&rezerwacja=42')
  })

  it('otwiera kartę gościa bez drugiego modala i zachowuje dokładny returnTo oraz szkic', async () => {
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => {})
    render(<ReservationsWorkspace />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Notatka dnia' }), {
      target: { value: 'Nie zgubić prośby o stolik przy oknie' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Baza/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Otwórz rezerwację Kowalskiej' }))
    await waitFor(() => expect(screen.getByTestId('today-reservation')).toHaveTextContent('42'))
    const reservationHash = window.location.hash

    fireEvent.click(screen.getByRole('button', { name: 'Profil gościa' }))

    expect(await screen.findByRole('dialog', { name: 'Karta gościa' })).toHaveTextContent('42')
    expect(window.location.hash).toContain('gosc=42')
    expect(window.history.state?.lokaloReservationReturnTo).toMatchObject({
      view: 'today',
      date: '2026-08-21',
      reservationId: 42,
      profileReservationId: null,
    })
    expect(screen.getByTestId('today-suspended')).toHaveTextContent('true')
    expect(screen.getByRole('textbox', { name: 'Notatka dnia' })).toHaveValue(
      'Nie zgubić prośby o stolik przy oknie',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Wróć do rezerwacji' }))
    expect(back).toHaveBeenCalledTimes(1)

    act(() => {
      window.history.replaceState(window.history.state, '', reservationHash)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Karta gościa' })).not.toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: 'Notatka dnia' })).toHaveValue(
      'Nie zgubić prośby o stolik przy oknie',
    )
  })

  it('blokuje Browser Back dla brudnego profilu bez duplikowania historii', async () => {
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => {})
    const forward = vi.spyOn(window.history, 'forward').mockImplementation(() => {})
    confirmMock.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    render(<ReservationsWorkspace />)

    fireEvent.click(screen.getByRole('button', { name: /Baza/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Otwórz rezerwację Kowalskiej' }))
    await waitFor(() => expect(screen.getByTestId('today-reservation')).toHaveTextContent('42'))
    const reservationHash = window.location.hash
    const reservationState = { ...(window.history.state || {}) }

    fireEvent.click(screen.getByRole('button', { name: 'Profil gościa' }))
    const profileHash = window.location.hash
    const profileState = { ...(window.history.state || {}) }
    fireEvent.click(await screen.findByRole('button', { name: 'Zmień profil testowo' }))

    act(() => {
      window.history.replaceState(reservationState, '', reservationHash)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(forward).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('dialog', { name: 'Karta gościa' })).toBeInTheDocument()

    act(() => {
      window.history.replaceState(profileState, '', profileHash)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await waitFor(() => expect(confirmMock).toHaveBeenCalledTimes(1))
    expect(back).not.toHaveBeenCalled()
    expect(window.location.hash).toBe(profileHash)

    act(() => {
      window.history.replaceState(reservationState, '', reservationHash)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(forward).toHaveBeenCalledTimes(2)
    act(() => {
      window.history.replaceState(profileState, '', profileHash)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await waitFor(() => expect(confirmMock).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(back).toHaveBeenCalledTimes(1))

    act(() => {
      window.history.replaceState(reservationState, '', reservationHash)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Karta gościa' })).not.toBeInTheDocument())
    expect(window.location.hash).toBe(reservationHash)
    expect(forward).toHaveBeenCalledTimes(2)
  })

  it('lock purge natychmiast usuwa profil, zaznaczenie i szkic, zachowując bezpieczny dzień', async () => {
    render(<ReservationsWorkspace />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Notatka dnia' }), {
      target: { value: 'PII tylko do bieżącej sesji operatora' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Baza/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Otwórz rezerwację Kowalskiej' }))
    await waitFor(() => expect(screen.getByTestId('today-reservation')).toHaveTextContent('42'))
    fireEvent.click(screen.getByRole('button', { name: 'Profil gościa' }))
    expect(await screen.findByRole('dialog', { name: 'Karta gościa' })).toBeInTheDocument()

    act(() => {
      purgeReservationPrivacy({
        reason: 'workstation-locked',
        preserveSafeRoute: true,
        broadcast: false,
      })
    })

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Karta gościa' })).not.toBeInTheDocument())
    expect(window.location.hash).toContain('/dzisiaj?data=2026-08-21')
    expect(window.location.hash).not.toContain('rezerwacja=')
    expect(window.location.hash).not.toContain('gosc=')
    expect(screen.getByTestId('today-reservation')).toHaveTextContent('brak')
    expect(screen.getByRole('textbox', { name: 'Notatka dnia' })).toHaveValue('')
  })

  it('purge abortuje resolver deep linku i nie pozwala spóźnionej odpowiedzi odtworzyć PII', async () => {
    let resolveReservation
    let requestSignal
    apiMock.mockImplementationOnce((_path, _method, _body, options) => {
      requestSignal = options.signal
      return new Promise((resolve) => { resolveReservation = resolve })
    })
    setHash('#/rezerwacje/dzisiaj?data=2026-08-17&rezerwacja=42')

    render(<ReservationsWorkspace />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1))

    act(() => {
      purgeReservationPrivacy({ reason: 'logout', broadcast: false })
    })

    expect(requestSignal.aborted).toBe(true)
    expect(window.location.hash).not.toContain('rezerwacja=')
    expect(screen.getByTestId('today-reservation')).toHaveTextContent('brak')

    await act(async () => {
      resolveReservation({ id: 42, data: '2026-08-21', nazwisko: 'Kowalska' })
      await Promise.resolve()
    })

    expect(window.location.hash).not.toContain('rezerwacja=')
    expect(screen.getByTestId('today-reservation')).toHaveTextContent('brak')
  })
})
