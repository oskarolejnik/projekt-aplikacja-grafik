// @vitest-environment jsdom
import { afterEach, describe, it, expect } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import Produkt from './Produkt'

afterEach(cleanup)

describe('Landing sprzedażowy (Produkt)', () => {
  it('pokazuje hero z propozycją wartości', () => {
    const { container } = render(<Produkt />)
    expect(container.textContent).toContain('jednym systemie')
    expect(container.textContent).toContain('Excela')
  })

  it('pokazuje wszystkie 5 pakietów', () => {
    render(<Produkt />)
    for (const tier of ['Darmowy', 'Basic', 'Pro', 'Premium', 'Enterprise']) {
      expect(screen.getByRole('heading', { name: tier })).toBeInTheDocument()
    }
  })

  it('domyślnie pokazuje ceny roczne + dodatek POS + wycenę', () => {
    const { container } = render(<Produkt />)
    const t = container.textContent
    for (const s of ['99', '199', '349', 'wycena', '149 zł']) {
      expect(t).toContain(s)
    }
  })

  it('ma przełącznik miesięcznie/rocznie i przełącza rozliczenie', () => {
    const { container } = render(<Produkt />)
    expect(screen.getByText('Rocznie')).toBeInTheDocument()
    const mies = screen.getByText('Miesięcznie')
    fireEvent.click(mies)
    expect(container.textContent).toContain('rozliczane co miesiąc')
  })

  it('wyróżnia plan flagowy (Pro) i ma sekcję FAQ', () => {
    const { container } = render(<Produkt />)
    expect(screen.getByText('Najczęściej wybierany')).toBeInTheDocument()
    expect(container.textContent).toContain('Częste pytania')
    expect(container.textContent).toContain('Muszę mieć system POS?')
  })

  it('eksponuje kluczowe moduły i CTA', () => {
    const { container } = render(<Produkt />)
    const t = container.textContent
    for (const f of ['Auto-grafik', 'Strażnik prawa pracy', 'Giełda wymiany zmian', 'Rezerwacje']) {
      expect(t).toContain(f)
    }
    expect(t).toContain('Umów demo')
    expect(t).toContain('Zacznij za darmo')
  })
})
