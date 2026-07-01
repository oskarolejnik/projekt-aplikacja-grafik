// @vitest-environment jsdom
import { afterEach, describe, it, expect } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import Produkt from './Produkt'

afterEach(cleanup)

describe('Strona produktu (Produkt)', () => {
  it('pokazuje hero z propozycją wartości', () => {
    render(<Produkt />)
    expect(screen.getByText(/Zastąp Excel/)).toBeInTheDocument()
    expect(screen.getByText(/jednym systemem/)).toBeInTheDocument()
  })

  it('pokazuje wszystkie 5 planów cennika', () => {
    render(<Produkt />)
    for (const tier of ['Darmowy', 'Basic', 'Pro', 'Premium', 'Enterprise']) {
      expect(screen.getByRole('heading', { name: tier })).toBeInTheDocument()
    }
  })

  it('pokazuje ceny planów i dodatek POS', () => {
    const { container } = render(<Produkt />)
    const t = container.textContent
    for (const cena of ['0 zł', '99 zł', '199 zł', '349 zł', 'wycena', '149 zł']) {
      expect(t).toContain(cena)
    }
  })

  it('wyróżnia plan flagowy (Pro) badge „Najpopularniejszy"', () => {
    render(<Produkt />)
    expect(screen.getByText('Najpopularniejszy')).toBeInTheDocument()
  })

  it('ma sekcję funkcji (min. 6) i CTA demo', () => {
    const { container } = render(<Produkt />)
    const t = container.textContent
    for (const f of ['Auto-grafik', 'wypłaty', 'Rozliczenia kasowe', 'Rezerwacje', 'Imprezy', 'White-label']) {
      expect(t).toContain(f)
    }
    expect(t).toContain('Umów demo')
  })
})
