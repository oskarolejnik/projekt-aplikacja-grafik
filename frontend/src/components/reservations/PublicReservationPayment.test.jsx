// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import PublicReservationPayment from './PublicReservationPayment'

afterEach(cleanup)

describe('PublicReservationPayment', () => {
  it('pokazuje jednoznaczne CTA dla oczekującego zadatku', () => {
    render(<PublicReservationPayment payment={{
      status: 'oczekuje',
      kind: 'deposit',
      amount_minor: 12000,
      currency: 'pln',
      checkout_url: 'https://checkout.stripe.test/session',
    }} />)

    expect(screen.getByRole('heading', { name: 'Opłać zadatek' })).toBeTruthy()
    expect(screen.getByText(/120,00\s*zł/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Przejdź do bezpiecznej płatności' }).getAttribute('href'))
      .toBe('https://checkout.stripe.test/session')
  })

  it('nie przedstawia preautoryzacji jako pobranej płatności', () => {
    render(<PublicReservationPayment payment={{
      status: 'autoryzowana',
      kind: 'preauth',
      amount_minor: 20000,
      currency: 'pln',
    }} />)

    expect(screen.getByRole('heading', { name: 'Kwota została zablokowana' })).toBeTruthy()
    expect(screen.getByText(/Środki nie zostały jeszcze pobrane/i)).toBeTruthy()
  })

  it('po błędzie oferuje bezpieczną ponowną próbę tylko dla polityki ponowienia', () => {
    const retry = vi.fn()
    render(<PublicReservationPayment payment={{
      status: 'nieudana',
      kind: 'deposit',
      amount_minor: 5000,
      po_niepowodzeniu: 'ponow',
    }} onRetry={retry} />)

    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('nie udaje Stripe w jawnym trybie demonstracyjnym', () => {
    render(<PublicReservationPayment payment={{
      status: 'oczekuje',
      kind: 'deposit',
      amount_minor: 5000,
      link: '/?platnosc=sandbox&rezerwuj',
      tryb_demo: true,
    }} />)

    expect(screen.getByRole('link', { name: 'Otwórz płatność demonstracyjną' })).toBeTruthy()
    expect(screen.getByText(/żadne środki nie zostaną pobrane/i)).toBeTruthy()
    expect(screen.queryByText(/obsługuje Stripe/i)).toBeNull()
  })

  it('po anulowaniu pokazuje oczekujący zwrot zamiast starego sukcesu', () => {
    render(<PublicReservationPayment payment={{
      status: 'oplacona',
      kind: 'deposit',
      amount_minor: 5000,
      refund_status: 'oczekuje',
    }} />)

    expect(screen.getByRole('heading', { name: 'Zwrot jest przetwarzany' })).toBeTruthy()
    expect(screen.queryByText('Nie musisz nic więcej robić.')).toBeNull()
  })
})
