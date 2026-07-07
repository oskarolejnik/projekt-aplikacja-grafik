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
  fireEvent.click(screen.getByText('Dalej'))
}

describe('KreatorLokalu (plany + karta na trialu)', () => {
  it('ścieżka płatna (Pro): konto → typ → plan → moduły → KARTA → trial', async () => {
    apiMock.mockResolvedValue({ tryb: 'trial-karta', status: 'zrealizowana',
      url: 'http://h:8100/?login', plan: 'pro', karta_ostatnie4: '4242' })
    render(<KreatorLokalu planStart="pro" />)
    wypelnijKonto()
    fireEvent.click(await screen.findByText('Pizzeria'))          // typ → plan (Pro wstępnie)
    fireEvent.click(await screen.findByText('Dalej'))             // plan → moduły
    fireEvent.click(await screen.findByText(/Dalej — karta/))     // moduły → karta (plan płatny)
    fireEvent.change(await screen.findByPlaceholderText(/4242 4242 4242 4242/), { target: { value: '4242 4242 4242 4242' } })
    fireEvent.change(screen.getByPlaceholderText('12/30'), { target: { value: '12/30' } })
    fireEvent.change(screen.getByPlaceholderText('123'), { target: { value: '123' } })
    fireEvent.click(screen.getByText(/Rozpocznij 14 dni za darmo/))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/online/rejestracja', 'POST',
      expect.objectContaining({
        email: 'wlasciciel@lokal.pl', plan: 'pro', nazwa_lokalu: 'Moja Knajpa',
        karta: expect.objectContaining({ exp_miesiac: 12, exp_rok: 30, cvc: '123' }),
      })))
  })

  it('ścieżka darmowa: konto → typ → plan(Darmowy) → moduły → utwórz (bez karty)', async () => {
    apiMock.mockResolvedValue({ tryb: 'darmowy', status: 'zrealizowana', url: 'http://h:8100/?login', plan: 'free' })
    render(<KreatorLokalu />)
    wypelnijKonto()
    fireEvent.click(await screen.findByText('Pizzeria'))
    fireEvent.click(await screen.findByText('Darmowy'))           // wybór planu darmowego
    fireEvent.click(screen.getByText('Dalej'))                    // plan → moduły
    fireEvent.click(await screen.findByText(/Utwórz lokal/))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/online/rejestracja', 'POST',
      expect.objectContaining({ plan: 'darmowy', email: 'wlasciciel@lokal.pl' })))
    // Bez kroku karty — żadne pole karty nie zostało pokazane.
    expect(screen.queryByPlaceholderText(/4242/)).not.toBeInTheDocument()
  })

  it('walidacja kroku konto: zły e-mail nie przechodzi dalej', () => {
    render(<KreatorLokalu />)
    fireEvent.change(screen.getByPlaceholderText(/Bistro Zdrój/), { target: { value: 'Moja Knajpa' } })
    fireEvent.change(screen.getByPlaceholderText(/jan@lokal\.pl/), { target: { value: 'bez-malpy' } })
    fireEvent.change(screen.getByPlaceholderText(/min. 8 znaków/), { target: { value: 'Haslo123!' } })
    fireEvent.click(screen.getByText('Dalej'))
    expect(screen.getByText(/prawidłowy e-mail/)).toBeInTheDocument()
  })
})
