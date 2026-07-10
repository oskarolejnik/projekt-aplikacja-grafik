// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

vi.mock('./Grafik', async () => {
  const { useState } = await import('react')

  return {
    default: () => {
      const [notatka, setNotatka] = useState('')

      return (
        <div>
          <div>Widok grafiku</div>
          <label>
            Notatka grafiku
            <input value={notatka} onChange={(event) => setNotatka(event.target.value)} />
          </label>
        </div>
      )
    },
  }
})
vi.mock('./Wymagania', () => ({ default: () => <div>Widok planu obsady</div> }))
vi.mock('./Dyspozycje', () => ({ default: () => <div>Widok dyspozycji</div> }))

import GrafikWorkspace from './GrafikWorkspace'

afterEach(cleanup)

describe('GrafikWorkspace', () => {
  it('pokazuje tylko aktywny etap planowania i komunikuje wybór', () => {
    render(<GrafikWorkspace />)

    expect(screen.getByRole('group', { name: 'Obszar planowania grafiku' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Grafik' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('region', { name: 'Grafik' })).toBeVisible()
    expect(screen.queryByText('Widok planu obsady')).not.toBeInTheDocument()
    expect(screen.queryByText('Widok dyspozycji')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Plan obsady' }))
    expect(screen.getByRole('button', { name: 'Plan obsady' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('region', { name: 'Plan obsady' })).toBeVisible()
    expect(screen.getByText('Widok grafiku').closest('section')).not.toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Dyspozycje' }))
    expect(screen.getByRole('region', { name: 'Dyspozycje' })).toBeVisible()
    expect(screen.getByText('Widok planu obsady').closest('section')).not.toBeVisible()
  })

  it('zachowuje lokalny stan widoku po zmianie etapu', () => {
    render(<GrafikWorkspace />)

    const notatka = screen.getByRole('textbox', { name: 'Notatka grafiku' })
    fireEvent.change(notatka, { target: { value: 'Obsada weekendowa' } })

    fireEvent.click(screen.getByRole('button', { name: 'Plan obsady' }))
    expect(notatka.closest('section')).not.toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: 'Grafik' }))
    expect(screen.getByRole('textbox', { name: 'Notatka grafiku' })).toHaveValue('Obsada weekendowa')
  })
})
