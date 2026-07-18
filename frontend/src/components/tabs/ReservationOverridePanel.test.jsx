// @vitest-environment jsdom
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ReservationOverridePanel from './ReservationOverridePanel'

vi.mock('../../lib/icons', () => ({ Icon: ({ name }) => <span aria-hidden="true">{name}</span> }))

function ControlledPanel({ onConfirm, ...props }) {
  const [value, setValue] = useState({ powod: '', notatka: '' })
  return (
    <ReservationOverridePanel
      availability={{
        violations: [{
          rule: 'pacing_reservations',
          code: 'PACING_RESERVATION_LIMIT',
          limit: 4,
          observed: 4,
          projected: 5,
          message: 'Limit nowych rezerwacji w ciągu 30 minut',
          scope: { type: 'room_channel', sala_id: 2, sala_nazwa: 'Ogród', kanal: 'wewnetrzna' },
        }],
      }}
      value={value}
      onChange={setValue}
      onConfirm={onConfirm}
      onCancel={() => {}}
      {...props}
    />
  )
}

describe('ReservationOverridePanel', () => {
  afterEach(() => cleanup())

  it('wyjaśnia przekroczenie i wymaga jawnego powodu przed potwierdzeniem', () => {
    const onConfirm = vi.fn()
    render(<ControlledPanel onConfirm={onConfirm} />)

    expect(screen.getByText('Limit nowych rezerwacji w ciągu 30 minut')).toBeInTheDocument()
    expect(screen.getByText('Limit: 4 · teraz: 4 · po operacji: 5')).toBeInTheDocument()
    expect(screen.getByText('Ogród · telefon / obsługa')).toBeInTheDocument()

    const submit = screen.getByRole('button', { name: 'Zapisz mimo limitu' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'operational_decision' } })
    fireEvent.change(screen.getByLabelText(/Notatka/), { target: { value: 'Dodatkowa obsada na sali' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)

    expect(onConfirm).toHaveBeenCalledWith({
      powod: 'operational_decision',
      notatka: 'Dodatkowa obsada na sali',
      potwierdzone: true,
    })
  })

  it('dla innego powodu wymaga krótkiej notatki', () => {
    render(<ControlledPanel onConfirm={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'other' } })
    expect(screen.getByRole('button', { name: 'Zapisz mimo limitu' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Notatka/), { target: { value: 'Wyjątek potwierdzony przez właściciela' } })
    expect(screen.getByRole('button', { name: 'Zapisz mimo limitu' })).toBeEnabled()
  })

  it('na aktywnym stanowisku wymaga dokładnie 6 cyfr i przekazuje PIN tylko do jednego potwierdzenia', () => {
    const onConfirm = vi.fn()
    render(
      <ControlledPanel
        onConfirm={onConfirm}
        requiresPin
        actionLabel="Potwierdź PIN-em i zapisz"
      />,
    )

    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'operational_decision' } })
    const pin = screen.getByLabelText('Twój 6-cyfrowy PIN')
    const submit = screen.getByRole('button', { name: 'Potwierdź PIN-em i zapisz' })

    fireEvent.change(pin, { target: { value: '12a34' } })
    expect(pin).toHaveValue('1234')
    expect(submit).toBeDisabled()

    fireEvent.change(pin, { target: { value: '1234567' } })
    expect(pin).toHaveValue('123456')
    expect(submit).toBeEnabled()
    fireEvent.click(submit)

    expect(pin).toHaveValue('')
    expect(onConfirm).toHaveBeenCalledWith({
      powod: 'operational_decision',
      notatka: null,
      potwierdzone: true,
    }, { pin: '123456' })
  })

  it('po blokadzie PIN zachowuje powód, pokazuje błąd przy polu i odliczanie', async () => {
    render(
      <ControlledPanel
        onConfirm={vi.fn()}
        requiresPin
        reauthError="Nieprawidłowy PIN."
        retryAfter={30}
        actionLabel="Potwierdź PIN-em i zapisz"
      />,
    )

    fireEvent.change(screen.getByLabelText('Powód przekroczenia'), { target: { value: 'guest_request' } })
    expect(screen.getByLabelText('Powód przekroczenia')).toHaveValue('guest_request')
    expect(screen.getByRole('alert').parentElement).toHaveTextContent('Nieprawidłowy PIN. Spróbuj ponownie za 30 s.')
    await waitFor(() => expect(screen.getByLabelText('Twój 6-cyfrowy PIN')).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Potwierdź PIN-em i zapisz' })).toBeDisabled()
  })
})
