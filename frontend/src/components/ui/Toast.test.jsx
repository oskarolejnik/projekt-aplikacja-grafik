// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { ToastProvider, useToast } from './Toast'

afterEach(cleanup)

// Konsument wystawiający toast()/confirm() na przyciskach — testujemy przez realny UI.
let wynikConfirm
function Konsument() {
  const { toast, confirm } = useToast()
  return (
    <div>
      <button onClick={() => toast('Zapisano zmiany!', 'success')}>pokaz-toast</button>
      <button onClick={() => toast('Nie udało się zapisać.', 'error')}>pokaz-error</button>
      <button onClick={async () => { wynikConfirm = await confirm('Na pewno usunąć?') }}>pokaz-confirm</button>
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

  it('confirm() → „Anuluj" rozwiązuje Promise wartością false', async () => {
    wynikConfirm = undefined
    render_()
    fireEvent.click(screen.getByRole('button', { name: 'pokaz-confirm' }))
    await screen.findByRole('alertdialog')
    fireEvent.click(screen.getByRole('button', { name: 'Anuluj' }))
    await waitFor(() => expect(wynikConfirm).toBe(false))
  })
})
