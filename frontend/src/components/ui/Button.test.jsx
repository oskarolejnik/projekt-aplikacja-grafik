// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { Button } from './Button'

afterEach(cleanup)

describe('Button', () => {
  it('renderuje treść dziecka', () => {
    render(<Button>Zapisz</Button>)
    const button = screen.getByRole('button', { name: 'Zapisz' })
    expect(button).toBeInTheDocument()
    expect(button).toHaveAttribute('type', 'button')
    expect(button.className).toContain('min-h-11')
    expect(button.className).toContain('min-w-11')
  })

  it('woła onClick po kliknięciu', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Klik</Button>)
    fireEvent.click(screen.getByRole('button', { name: 'Klik' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('disabled oznacza przycisk jako wyłączony', () => {
    render(<Button disabled>X</Button>)
    expect(screen.getByRole('button', { name: 'X' })).toBeDisabled()
  })

  it('stosuje klasy wariantu i rozmiaru', () => {
    render(<Button variant="danger" size="lg">Usuń</Button>)
    const btn = screen.getByRole('button', { name: 'Usuń' })
    expect(btn.className).toContain('bg-danger')  // variant=danger
    expect(btn.className).toContain('text-base')  // size=lg
  })

  it('przekazuje dodatkową klasę', () => {
    render(<Button className="moja-klasa">Y</Button>)
    expect(screen.getByRole('button', { name: 'Y' }).className).toContain('moja-klasa')
  })

  it('pozwala jawnie ustawić typ submit', () => {
    render(<Button type="submit">Wyślij</Button>)
    expect(screen.getByRole('button', { name: 'Wyślij' })).toHaveAttribute('type', 'submit')
  })

  it('pokazuje stabilny stan ładowania i blokuje kolejne kliknięcia', () => {
    const onClick = vi.fn()
    const { container, rerender } = render(
      <Button loading loadingLabel="Zapisuję…" onClick={onClick}>Zapisz</Button>,
    )

    const loadingButton = screen.getByRole('button', { name: 'Zapisuję…' })
    expect(loadingButton).toBeDisabled()
    expect(loadingButton).toHaveAttribute('aria-busy', 'true')
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.getByText('Zapisz')).toHaveClass('opacity-0')
    expect(screen.getByText('Zapisuję…').parentElement).toHaveClass('col-start-1', 'row-start-1')

    fireEvent.click(loadingButton)
    expect(onClick).not.toHaveBeenCalled()

    rerender(<Button loadingLabel="Zapisuję…" onClick={onClick}>Zapisz</Button>)
    const readyButton = screen.getByRole('button', { name: 'Zapisz' })
    expect(readyButton).not.toBeDisabled()
    expect(readyButton).not.toHaveAttribute('aria-busy')
    expect(screen.getByText('Zapisuję…').parentElement).toHaveClass('invisible')
    fireEvent.click(readyButton)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('bez loadingLabel zachowuje dotychczasową dostępną nazwę', () => {
    render(<Button loading>Zapisz</Button>)
    expect(screen.getByRole('button', { name: 'Zapisz' })).toHaveAttribute('aria-busy', 'true')
  })
})
