// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, logoutMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  logoutMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/AuthContext', () => ({ useAuth: () => ({ logout: logoutMock }) }))

import WorkstationSetup from './WorkstationSetup'

describe('WorkstationSetup', () => {
  beforeEach(() => {
    apiMock.mockReset()
    logoutMock.mockReset()
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/reservation-workstations' && method === 'GET') return Promise.resolve([])
      if (path === '/reservation-workstations/operators') return Promise.reject(new Error('Brak stanowiska'))
      if (path === '/reservation-workstations' && method === 'POST') return Promise.resolve({
        id: 'station-1',
        name: 'Recepcja główna',
        active: true,
        idle_timeout_seconds: 300,
      })
      return Promise.reject(new Error('Nieoczekiwane żądanie'))
    })
  })

  it('rejestruje bieżący komputer z wybranym timeoutem i pokazuje następny krok', async () => {
    render(<WorkstationSetup />)
    fireEvent.change(screen.getByLabelText('Nazwa stanowiska'), { target: { value: 'Recepcja główna' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ustaw ten komputer' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/reservation-workstations', 'POST', {
      name: 'Recepcja główna',
      idle_timeout_seconds: 300,
    }))
    expect(await screen.findByText(/Ten komputer jest gotowy/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Otwórz stanowisko' })).toBeInTheDocument()
  })
})
