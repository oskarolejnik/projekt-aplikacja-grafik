// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, reloadDictsMock, toastMock, confirmMock, dataState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  reloadDictsMock: vi.fn(),
  toastMock: vi.fn(),
  confirmMock: vi.fn(),
  dataState: { users: [] },
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/DataContext', () => ({
  useData: () => ({ pracownicy: [], reloadDicts: reloadDictsMock }),
}))
vi.mock('../ui/Toast', () => ({
  useToast: () => ({ toast: toastMock, confirm: confirmMock }),
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import Konta from './Konta'

const manager = {
  id: 7,
  login: 'manager',
  rola: 'szef',
  aktywny: true,
  pracownik_id: null,
  imie: 'Marta',
  nazwisko: 'Nowak',
  preset: null,
  uprawnienia: ['grafik.podglad', 'raporty.podglad'],
  uprawnienia_override: {},
}

const admin = {
  id: 1,
  login: 'admin',
  rola: 'admin',
  aktywny: true,
  pracownik_id: null,
  uprawnienia: [],
  uprawnienia_override: {},
}

const employee = {
  id: 9,
  login: 'pracownik',
  rola: 'employee',
  aktywny: true,
  pracownik_id: null,
  uprawnienia: ['me.grafik'],
  uprawnienia_override: {},
}

const reception = {
  ...manager,
  id: 12,
  login: 'recepcja',
  imie: 'Ola',
  nazwisko: 'Lis',
  preset: 'recepcja_host',
  reservation_pin_configured: false,
  uprawnienia: [
    'rezerwacje.operacje',
    'rezerwacje.host',
    'rezerwacje.nadpisuj_limity',
    'rezerwacje.dane_kontaktowe',
  ],
}

describe('Konta permissions', () => {
  beforeEach(() => {
    dataState.users = [{ ...manager }, { ...admin }, { ...employee }]
    reloadDictsMock.mockResolvedValue({ pracownicy: [], stanowiska: [] })
    confirmMock.mockResolvedValue(true)
    apiMock.mockImplementation((path, method, body) => {
      if (path === '/zaproszenia') return Promise.resolve({ zaproszenia: [] })
      if (path === '/users') return Promise.resolve(dataState.users)
      if (path === '/users/7/uprawnienia' && method === 'PUT') {
        if (body.preset === 'recepcja_host') {
          return Promise.resolve({
            ...manager,
            preset: 'recepcja_host',
            uprawnienia: [
              'rezerwacje.operacje',
              'rezerwacje.host',
              'rezerwacje.nadpisuj_limity',
              'rezerwacje.dane_kontaktowe',
            ],
          })
        }
        const overrides = body.uprawnienia_override
        const permissions = new Set(manager.uprawnienia)
        Object.entries(overrides).forEach(([key, enabled]) => enabled ? permissions.add(key) : permissions.delete(key))
        return Promise.resolve({
          ...manager,
          uprawnienia: [...permissions],
          uprawnienia_override: overrides,
        })
      }
      return Promise.resolve({})
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('pokazuje zwijany dostęp tylko dla managera i zapisuje pełną mapę wyjątków', async () => {
    dataState.users[0] = {
      ...manager,
      uprawnienia_override: { 'imprezy.podglad': false },
    }
    render(<Konta />)

    await screen.findByText('manager')
    expect(screen.getAllByText('Dostęp')).toHaveLength(1)
    fireEvent.click(screen.getByText('Dostęp'))

    const grafik = screen.getByRole('switch', { name: /Grafik i stoły/ })
    expect(grafik).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(grafik)

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/users/7/uprawnienia', 'PUT', {
      uprawnienia_override: { 'imprezy.podglad': false, 'grafik.podglad': false },
    }))
    await waitFor(() => expect(screen.getByRole('switch', { name: /Grafik i stoły/ })).toHaveAttribute('aria-checked', 'false'))
  })

  it('przywraca ustawienia roli pustą mapą wyjątków', async () => {
    dataState.users = [{
      ...manager,
      uprawnienia: ['raporty.podglad'],
      uprawnienia_override: { 'grafik.podglad': false },
    }]
    render(<Konta />)

    await screen.findByText('manager')
    fireEvent.click(screen.getByText('Dostęp'))
    fireEvent.click(screen.getByRole('button', { name: 'Przywróć ustawienia roli' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/users/7/uprawnienia', 'PUT', {
      uprawnienia_override: {},
    }))
  })

  it('tworzy nazwane konto Recepcja / Host jako szefa z gotowym presetem', async () => {
    render(<Konta />)
    await screen.findByText('manager')

    fireEvent.change(screen.getByLabelText('Login'), { target: { value: 'recepcja' } })
    fireEvent.change(screen.getByLabelText('Hasło startowe'), { target: { value: 'Start123!' } })
    fireEvent.change(screen.getByLabelText('Zakres pracy'), { target: { value: 'recepcja_host' } })
    expect(screen.getByText(/Konto otworzy prosty pulpit rezerwacji i hosta/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Utwórz konto' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/users', 'POST', {
      login: 'recepcja',
      haslo: 'Start123!',
      rola: 'szef',
      pracownik_id: null,
      preset: 'recepcja_host',
    }))
  })

  it('aplikuje preset istniejącemu kontu i czytelnie oznacza gotową Recepcję / Hosta', async () => {
    render(<Konta />)
    await screen.findByText('manager')

    fireEvent.click(screen.getByText('Dostęp'))
    fireEvent.click(screen.getByRole('button', { name: 'Zastosuj preset' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Zastąpi bieżący zakres dostępu'),
      expect.objectContaining({ confirmText: 'Zastosuj preset' }),
    ))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/users/7/uprawnienia', 'PUT', {
      preset: 'recepcja_host',
    }))
    expect(await screen.findByText('Aktywny preset')).toBeInTheDocument()
    expect(screen.getAllByText('Recepcja / Host').length).toBeGreaterThanOrEqual(1)
  })

  it('pokazuje kontrolę PIN-u wyłącznie dla dokładnego presetu Recepcja / Host', async () => {
    dataState.users = [
      { ...reception },
      { ...manager, reservation_pin_configured: true },
      { ...admin, reservation_pin_configured: true },
    ]

    render(<Konta />)
    await screen.findByText('recepcja')

    expect(screen.getAllByText('PIN stanowiska')).toHaveLength(1)
    expect(screen.getByLabelText(/Nowy PIN stanowiska/)).toHaveAttribute('type', 'password')
    expect(screen.getByText('Nieustawiony')).toBeInTheDocument()
  })

  it('nie oferuje zmiany PIN-u nieaktywnemu operatorowi', async () => {
    dataState.users = [{ ...reception, aktywny: false, reservation_pin_configured: true }]
    render(<Konta />)
    await screen.findByText('recepcja')

    expect(screen.getByText('Aktywuj konto, aby ustawić lub zmienić PIN.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zmień PIN' })).toBeDisabled()
    expect(screen.queryByLabelText(/Nowy PIN stanowiska/)).not.toBeInTheDocument()
  })

  it('waliduje i ustawia dokładnie 6 cyfr bez pozostawiania PIN-u w interfejsie', async () => {
    dataState.users = [{ ...reception }]
    render(<Konta />)
    await screen.findByText('recepcja')

    const pinInput = screen.getByLabelText(/Nowy PIN stanowiska/)
    fireEvent.change(pinInput, { target: { value: '12a34' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ustaw PIN' }))

    expect(screen.getByRole('alert')).toHaveTextContent('PIN musi mieć dokładnie 6 cyfr.')
    expect(apiMock.mock.calls.some(([path]) => path === '/users/12/reservation-pin')).toBe(false)

    fireEvent.change(pinInput, { target: { value: '12a34567' } })
    expect(pinInput).toHaveValue('123456')
    fireEvent.click(screen.getByRole('button', { name: 'Ustaw PIN' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/users/12/reservation-pin',
      'PUT',
      { pin: '123456' },
    ))
    expect(await screen.findByRole('status')).toHaveTextContent('PIN został ustawiony.')
    expect(screen.getByText('Ustawiony')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('123456')).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('123456')
  })

  it('usuwa skonfigurowany PIN po potwierdzeniu i aktualizuje stan konta lokalnie', async () => {
    dataState.users = [{ ...reception, reservation_pin_configured: true }]
    render(<Konta />)
    await screen.findByText('recepcja')

    expect(screen.queryByLabelText(/Nowy PIN stanowiska/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Usuń PIN' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Aktywne sesje tego operatora zostaną zablokowane'),
      expect.objectContaining({ confirmText: 'Usuń PIN', danger: true }),
    ))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/users/12/reservation-pin', 'DELETE'))
    expect(await screen.findByRole('status')).toHaveTextContent('PIN został usunięty.')
    expect(screen.getByText('Nieustawiony')).toBeInTheDocument()
    expect(screen.getByLabelText(/Nowy PIN stanowiska/)).toHaveValue('')
  })
})
