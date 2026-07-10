// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, toastMock } = vi.hoisted(() => ({ apiMock: vi.fn(), toastMock: vi.fn() }))

vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../components/ui/Card', () => ({
  Card: ({ children, className = '', ...props }) => <div className={className} {...props}>{children}</div>,
}))
vi.mock('../components/ui/Spinner', () => ({ Spinner: () => <span>Ładowanie</span> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import EmployeeHours from './EmployeeHours'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('EmployeeHours', () => {
  it('pokazuje godziny i wypłatę przed obsługą zaliczek', async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/me/godziny')) {
        return Promise.resolve({ suma_godzin: 8, do_wyplaty: 240, stanowiska: [], dni: [], aktywna_zmiana: null })
      }
      if (path.startsWith('/me/portfel')) {
        return Promise.resolve({ zarobek: 240, dostepna_zaliczka: 120, limit_procent: 50, zaliczki: [] })
      }
      if (path.startsWith('/me/napiwki')) return Promise.resolve({ suma: 0, dni: [] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<EmployeeHours />)

    const podsumowanie = await screen.findByText('Łącznie w miesiącu')
    const zaliczka = await screen.findByText(/Dostępna zaliczka:/)
    expect(podsumowanie.compareDocumentPosition(zaliczka) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText('08:00')).toBeInTheDocument()
    expect(screen.getAllByText('240,00 zł').length).toBeGreaterThan(0)
  })
})
