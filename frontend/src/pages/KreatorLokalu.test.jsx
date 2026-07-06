// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../lib/api', () => ({ api: apiMock }))

import KreatorLokalu from './KreatorLokalu'

afterEach(() => { cleanup(); vi.clearAllMocks() })

function wypelnijKonto() {
  fireEvent.change(screen.getByPlaceholderText(/Bistro Zdrój/), { target: { value: 'Moja Knajpa' } })
  fireEvent.change(screen.getByPlaceholderText(/jan@lokal\.pl/), { target: { value: 'wlasciciel@lokal.pl' } })
  fireEvent.change(screen.getByPlaceholderText(/min. 8 znaków/), { target: { value: 'Haslo123!' } })
  fireEvent.click(screen.getByText(/Dalej — typ lokalu/))
}

describe('KreatorLokalu (trial + pakiety)', () => {
  it('ścieżka płatna: konto → typ → plan(Pro) → moduły → checkout → opłać', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/online/rejestracja')
        return Promise.resolve({ tryb: 'platny', external_id: 'ext1', brutto: 244.77, plan: 'pro', provider: 'sandbox' })
      if (path === '/online/rejestracja/ext1/oplac')
        return Promise.resolve({ status: 'zrealizowana', url: 'http://h:8100/?login' })
      return Promise.resolve({})
    })
    render(<KreatorLokalu planStart="pro" />)
    wypelnijKonto()
    fireEvent.click(await screen.findByText('Pizzeria'))       // typ → krok plan
    fireEvent.click(await screen.findByText(/Dalej — moduły/)) // plan(Pro wstępnie) → moduły
    fireEvent.click(await screen.findByText(/Przejdź do płatności/))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/online/rejestracja', 'POST',
      expect.objectContaining({ email: 'wlasciciel@lokal.pl', plan: 'pro', nazwa_lokalu: 'Moja Knajpa' })))
    expect(await screen.findByText(/244\.77 zł/)).toBeInTheDocument()
    fireEvent.click(screen.getByText(/Zapłać/))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/online/rejestracja/ext1/oplac', 'POST'))
  })

  it('ścieżka trial (domyślna): stawia od razu bez płatności', async () => {
    apiMock.mockResolvedValue({ tryb: 'trial', status: 'zrealizowana', url: 'http://h:8100/?login' })
    render(<KreatorLokalu />)                                  // brak planStart → domyślnie trial
    wypelnijKonto()
    fireEvent.click(await screen.findByText('Pizzeria'))
    fireEvent.click(await screen.findByText(/Dalej — moduły/)) // trial wybrany domyślnie
    fireEvent.click(await screen.findByText(/Rozpocznij 14 dni za darmo/))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/online/rejestracja', 'POST', expect.objectContaining({ trial: true, email: 'wlasciciel@lokal.pl' })))
  })

  it('walidacja kroku konto: zły e-mail nie przechodzi dalej', () => {
    render(<KreatorLokalu />)
    fireEvent.change(screen.getByPlaceholderText(/Bistro Zdrój/), { target: { value: 'Moja Knajpa' } })
    fireEvent.change(screen.getByPlaceholderText(/jan@lokal\.pl/), { target: { value: 'bez-malpy' } })
    fireEvent.change(screen.getByPlaceholderText(/min. 8 znaków/), { target: { value: 'Haslo123!' } })
    fireEvent.click(screen.getByText(/Dalej — typ lokalu/))
    expect(screen.getByText(/prawidłowy adres e-mail/)).toBeInTheDocument()
  })
})
