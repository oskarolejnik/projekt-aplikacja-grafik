// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { act, render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { privacyState, subscribePurgeMock } = vi.hoisted(() => ({
  privacyState: { callback: null },
  subscribePurgeMock: vi.fn((callback) => {
    privacyState.callback = callback
    return () => {
      if (privacyState.callback === callback) privacyState.callback = null
    }
  }),
}))

vi.mock('../../lib/reservationPrivacy', () => ({
  subscribeReservationPrivacyPurge: subscribePurgeMock,
}))

import { ToastProvider, useToast } from './Toast'

afterEach(() => {
  cleanup()
  document.body.style.overflow = ''
  privacyState.callback = null
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

// Konsument wystawiający toast()/confirm() na przyciskach — testujemy przez realny UI.
let wynikConfirm
const cofnijMock = vi.fn()
function Konsument() {
  const { toast, confirm } = useToast()
  return (
    <div>
      <button onClick={() => toast('Zapisano zmiany!', 'success')}>pokaz-toast</button>
      <button onClick={() => toast('Nie udało się zapisać.', 'error')}>pokaz-error</button>
      <button onClick={() => toast('Wpis usunięty.', 'success', {
        duration: 8000,
        action: { label: 'Cofnij', onClick: cofnijMock },
      })}>pokaz-toast-z-akcja</button>
      <button onClick={() => toast('Nie zapisano zmian.', 'error', {
        action: { label: 'Ponów', onClick: cofnijMock },
      })}>pokaz-trwaly-toast-z-akcja</button>
      <button onClick={() => toast('Rezerwacja Anny Kowalskiej.', 'success', {
        scope: 'reservations',
        action: { label: 'Cofnij rezerwację', onClick: cofnijMock },
      })}>pokaz-toast-rezerwacji</button>
      <button onClick={async () => { wynikConfirm = await confirm('Na pewno usunąć?') }}>pokaz-confirm</button>
      <button onClick={async () => { wynikConfirm = await confirm('Usunąć rezerwację Anny Kowalskiej?') }}>pokaz-confirm-rezerwacji</button>
    </div>
  )
}

function render_() {
  return render(
    <ToastProvider><Konsument /></ToastProvider>,
  )
}

describe('ToastProvider / useToast', () => {
  it('toast() pokazuje komunikat', () => {
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-toast' }))
    expect(screen.getByText('Zapisano zmiany!')).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('błąd jest ogłaszany jako alert', () => {
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-error' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się zapisać.')
  })

  it('toast może wykonać jedną akcję i po niej znika', async () => {
    cofnijMock.mockReset()
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-toast-z-akcja' }))

    const action = screen.getByRole('button', { name: 'Cofnij' })
    expect(action).toHaveClass('min-h-11')
    fireEvent.click(action)

    expect(cofnijMock).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByText('Wpis usunięty.')).not.toBeInTheDocument())
  })

  it('respektuje własny czas i czyści timer przy zamknięciu', () => {
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout')
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-toast-z-akcja' }))

    const timerIndex = timeoutSpy.mock.calls.findIndex(([, duration]) => duration === 8000)
    expect(timerIndex).toBeGreaterThanOrEqual(0)
    const timer = timeoutSpy.mock.results[timerIndex].value
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }))
    expect(clearTimeoutSpy).toHaveBeenCalledWith(timer)
  })

  it('domyślnie nie wygasza toasta z akcją, ale zachowuje 4,2 s dla zwykłego komunikatu', () => {
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    render_()

    fireEvent.click(screen.getByRole('button', { name: 'pokaz-trwaly-toast-z-akcja' }))
    expect(screen.getByRole('button', { name: 'Ponów' })).toBeInTheDocument()
    expect(timeoutSpy.mock.calls.some(([, duration]) => duration === 4200)).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'pokaz-toast' }))
    expect(timeoutSpy.mock.calls.some(([, duration]) => duration === 4200)).toBe(true)
  })

  it('czyści aktywne timery przy odmontowaniu providera', () => {
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout')
    const view = render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-toast-z-akcja' }))

    const timerIndex = timeoutSpy.mock.calls.findIndex(([, duration]) => duration === 8000)
    const timer = timeoutSpy.mock.results[timerIndex].value
    view.unmount()
    expect(clearTimeoutSpy).toHaveBeenCalledWith(timer)
  })

  it('confirm() → „Potwierdź" rozwiązuje Promise wartością true', async () => {
    wynikConfirm = undefined
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-confirm' }))
    expect(await screen.findByRole('alertdialog', { name: 'Na pewno?' })).toBeInTheDocument()
    expect(screen.getByText('Na pewno usunąć?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Anuluj' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź' }))
    await waitFor(() => expect(wynikConfirm).toBe(true))
  })

  it('utrzymuje fokus wewnątrz dialogu', async () => {
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-confirm' }))
    await screen.findByRole('alertdialog')
    const anuluj = screen.getByRole('button', { name: 'Anuluj' })
    const potwierdz = screen.getByRole('button', { name: 'Potwierdź' })

    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(potwierdz).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(anuluj).toHaveFocus()
  })

  it('blokuje tło i oddaje fokus do kontrolki wywołującej po Escape', async () => {
    render_()
    const trigger = screen.getByRole('button', { name: 'pokaz-confirm' })
    trigger.focus()
    fireEvent.click(trigger)

    await screen.findByRole('alertdialog')
    expect(document.body.style.overflow).toBe('hidden')

    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(document.body.style.overflow).toBe('')
    expect(trigger).toHaveFocus()
  })

  it('confirm() → „Anuluj" rozwiązuje Promise wartością false', async () => {
    wynikConfirm = undefined
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-confirm' }))
    await screen.findByRole('alertdialog')
    fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }))
    await waitFor(() => expect(wynikConfirm).toBe(false))
  })

  it('purge anuluje aktywny confirm, nie przywraca fokusu do PII i usuwa tylko toasty rezerwacji', async () => {
    wynikConfirm = undefined
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-toast' }))
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-toast-rezerwacji' }))
    const trigger = screen.getByRole('button', { name: 'pokaz-confirm-rezerwacji' })
    trigger.focus()
    fireEvent.click(trigger)

    await screen.findByRole('alertdialog')
    expect(screen.getByText('Rezerwacja Anny Kowalskiej.')).toBeInTheDocument()

    act(() => privacyState.callback?.({ reason: 'workstation-locked' }))

    await waitFor(() => expect(wynikConfirm).toBe(false))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(screen.queryByText('Rezerwacja Anny Kowalskiej.')).not.toBeInTheDocument()
    expect(screen.getByText('Zapisano zmiany!')).toBeInTheDocument()
    expect(trigger).not.toHaveFocus()
    expect(cofnijMock).not.toHaveBeenCalled()
    expect(subscribePurgeMock).toHaveBeenCalled()
  })
})
