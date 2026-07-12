// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, establishSessionMock } = vi.hoisted(() => ({ apiMock: vi.fn(), establishSessionMock: vi.fn() }))
vi.mock('../lib/api', () => ({ api: apiMock }))
vi.mock('../lib/authTransition', () => ({ establishAuthenticatedSession: establishSessionMock }))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: vi.fn() }) }))

import Onboarding from './Onboarding'

afterEach(() => { cleanup(); vi.clearAllMocks() })

function wypelnijKonto() {
  fireEvent.change(screen.getByPlaceholderText('Moja Restauracja'), { target: { value: 'Testowa' } })
  fireEvent.change(screen.getByPlaceholderText(/jan@lokal\.pl/), { target: { value: 'admin@testowa.pl' } })
  fireEvent.change(screen.getByPlaceholderText(/min. 8 znaków/), { target: { value: 'Haslo123!' } })
  fireEvent.click(screen.getByText(/Dalej — wybór typu/))
}

describe('Kreator lokalu (Onboarding)', () => {
  it('krok konto → bootstrap → krok typ (siatka typów)', async () => {
    apiMock.mockResolvedValue({ access_token: 'tok' })
    render(<Onboarding />)
    wypelnijKonto()
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/onboarding/bootstrap', 'POST', expect.objectContaining({ email: 'admin@testowa.pl', nazwa_lokalu: 'Testowa' })))
    expect(establishSessionMock).toHaveBeenCalledWith('tok')
    // Krok „typ": widać popularne typy + kartę „Inny".
    expect(await screen.findByText('Pizzeria')).toBeInTheDocument()
    expect(screen.getByText('Karczma / restauracja regionalna')).toBeInTheDocument()
    expect(screen.getByText('Inny / od zera')).toBeInTheDocument()
  })

  it('wybór typu prowadzi do kroku moduły (z rdzeniem i CTA)', async () => {
    apiMock.mockResolvedValue({ access_token: 'tok' })
    render(<Onboarding />)
    wypelnijKonto()
    fireEvent.click(await screen.findByRole('button', { name: /Pizzeria/ }))
    expect(await screen.findByText('Zawsze włączone (rdzeń)')).toBeInTheDocument()
    expect(screen.getByText(/Zapisz i wejdź/)).toBeInTheDocument()
    // Zapis wysyła typ + preset modułów.
    fireEvent.click(screen.getByText(/Zapisz i wejdź/))
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/lokal/config', 'PUT', expect.objectContaining({ typ_lokalu: 'pizzeria', modul_imprezy: false, rezerwacje_online: true })))
  })

  it('walidacja: bez danych nie woła bootstrap', () => {
    render(<Onboarding />)
    fireEvent.click(screen.getByText(/Dalej — wybór typu/))
    expect(apiMock).not.toHaveBeenCalled()
  })
})
