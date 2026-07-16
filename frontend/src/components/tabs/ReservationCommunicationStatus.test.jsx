// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

vi.mock('../../lib/icons', () => ({ Icon: ({ name }) => <span data-icon={name} aria-hidden /> }))

import ReservationCommunicationStatus from './ReservationCommunicationStatus'

describe('ReservationCommunicationStatus', () => {
  it('łączy stan, kanał i liczbę problemów w czytelnym statusie', () => {
    render(<ReservationCommunicationStatus summary={{
      state: 'uncertain',
      channel: 'oba',
      attention_count: 2,
    }} />)

    const status = screen.getByLabelText('Sprawdź wynik, e-mail + SMS, 2 wiadomości wymagają uwagi')
    expect(status).toHaveTextContent(/Sprawdź wynik.*e-mail \+ SMS/)
    expect(status).toHaveTextContent('2')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(status.querySelector('[data-icon="warning"]')).toBeInTheDocument()
  })

  it('używa live regionu wyłącznie tam, gdzie status faktycznie się zmienia', () => {
    render(<ReservationCommunicationStatus summary={null} live />)

    expect(screen.getByRole('status', { name: 'Brak wiadomości' })).toHaveTextContent('Brak wiadomości')
  })
})
