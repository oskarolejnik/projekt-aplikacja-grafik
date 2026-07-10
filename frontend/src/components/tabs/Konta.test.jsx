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

describe('Konta permissions', () => {
  beforeEach(() => {
    dataState.users = [{ ...manager }, { ...admin }, { ...employee }]
    reloadDictsMock.mockResolvedValue({ pracownicy: [], stanowiska: [] })
    confirmMock.mockResolvedValue(true)
    apiMock.mockImplementation((path, method, body) => {
      if (path === '/zaproszenia') return Promise.resolve({ zaproszenia: [] })
      if (path === '/users') return Promise.resolve(dataState.users)
      if (path === '/users/7/uprawnienia' && method === 'PUT') {
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
})
