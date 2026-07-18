// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { WorkstationGate } from './WorkstationGate'

const operators = [
  { id: 7, name: 'Ola Nowak', role: 'Recepcja / Host' },
  { id: 11, name: 'Jan Kowalski', role: 'Manager' },
]

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('WorkstationGate', () => {
  it('wybiera ostatniego operatora, fokusuje PIN i wysyła 6 cyfr klawiszem Enter', () => {
    const onUnlock = vi.fn()
    render(
      <WorkstationGate
        station={{ name: 'Recepcja główna' }}
        operators={operators}
        currentOperatorId={7}
        onUnlock={onUnlock}
        onUsePassword={vi.fn()}
      />,
    )

    expect(screen.getByText('Stanowisko · Recepcja główna')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Ola Nowak/ })).toBeChecked()

    const pin = screen.getByLabelText('PIN')
    expect(pin).toHaveFocus()
    expect(pin).toHaveAttribute('type', 'password')
    expect(pin).toHaveAttribute('inputmode', 'numeric')

    fireEvent.change(pin, { target: { value: '12a34567' } })
    expect(pin).toHaveValue('123456')
    fireEvent.keyDown(pin, { key: 'Enter', code: 'Enter' })
    fireEvent.submit(pin.closest('form'))

    expect(onUnlock).toHaveBeenCalledTimes(1)
    expect(onUnlock).toHaveBeenCalledWith({ userId: 7, pin: '123456' })
  })

  it('po zmianie operatora czyści PIN i przenosi fokus z powrotem do pola', () => {
    render(
      <WorkstationGate
        operators={operators}
        currentOperatorId={7}
        onUnlock={vi.fn()}
        onUsePassword={vi.fn()}
      />,
    )

    const pin = screen.getByLabelText('PIN')
    fireEvent.change(pin, { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('radio', { name: /Jan Kowalski/ }))

    expect(screen.getByRole('radio', { name: /Jan Kowalski/ })).toBeChecked()
    expect(pin).toHaveValue('')
    expect(pin).toHaveFocus()
  })

  it('pokazuje lokalny błąd i nie wysyła niepełnego PIN-u', () => {
    const onUnlock = vi.fn()
    render(
      <WorkstationGate
        operators={operators}
        currentOperatorId={7}
        onUnlock={onUnlock}
        onUsePassword={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByLabelText('PIN'), { target: { value: '123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Odblokuj' }))

    expect(screen.getByRole('alert')).toHaveTextContent('PIN musi mieć 6 cyfr.')
    expect(onUnlock).not.toHaveBeenCalled()
  })

  it('odlicza blokadę prób i udostępnia bezpieczne akcje awaryjne', () => {
    vi.useFakeTimers()
    const onUsePassword = vi.fn()
    const onForgetStation = vi.fn()
    render(
      <WorkstationGate
        operators={operators}
        currentOperatorId={7}
        error="Nieprawidłowy PIN."
        retryAfter={2}
        onUnlock={vi.fn()}
        onUsePassword={onUsePassword}
        onForgetStation={onForgetStation}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Nieprawidłowy PIN.')
    expect(screen.getByText('0:02')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Odblokuj' })).toBeDisabled()

    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByText('0:01')).toBeInTheDocument()
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByRole('button', { name: 'Odblokuj' })).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Zaloguj się hasłem' }))
    fireEvent.click(screen.getByRole('button', { name: 'Usuń powiązanie stanowiska' }))
    expect(onUsePassword).toHaveBeenCalledTimes(1)
    expect(onForgetStation).toHaveBeenCalledTimes(1)
  })

  it('bez przypisanych operatorów prowadzi do logowania hasłem', () => {
    const onUsePassword = vi.fn()
    render(<WorkstationGate operators={[]} onUnlock={vi.fn()} onUsePassword={onUsePassword} />)

    expect(screen.getByText('Brak operatorów przypisanych do tego stanowiska.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Odblokuj' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Zaloguj się hasłem' }))
    expect(onUsePassword).toHaveBeenCalledTimes(1)
  })
})
