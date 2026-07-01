import { describe, it, expect } from 'vitest'
import { generujOpcjeTygodni } from './weeks'

const DZIEN = 86400000
const start = (value) => new Date(value.split('|')[0])
const koniec = (value) => new Date(value.split('|')[1])

describe('generujOpcjeTygodni', () => {
  const { opcje, domyslny, biezacy, przyszly } = generujOpcjeTygodni()

  it('zwraca 8 tygodni (od -2 do +5) z wartościami i etykietami', () => {
    expect(opcje).toHaveLength(8)
    for (const o of opcje) {
      expect(o.value).toMatch(/^\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}$/)
      expect(typeof o.label).toBe('string')
      expect(o.label.length).toBeGreaterThan(0)
    }
  })

  it('każdy tydzień trwa 6 dni (środa → wtorek)', () => {
    for (const o of opcje) {
      expect((koniec(o.value) - start(o.value)) / DZIEN).toBe(6)
    }
  })

  it('kolejne tygodnie są przesunięte o 7 dni', () => {
    for (let i = 1; i < opcje.length; i++) {
      expect((start(opcje[i].value) - start(opcje[i - 1].value)) / DZIEN).toBe(7)
    }
  })

  it('bieżący = domyślny i istnieje w opcjach', () => {
    expect(biezacy).toBe(domyslny)
    expect(biezacy).toBeTruthy()
    expect(opcje.some((o) => o.value === biezacy)).toBe(true)
    expect(opcje.some((o) => o.value === przyszly)).toBe(true)
  })

  it('etykiety tagów: poprzedni/bieżący/przyszły', () => {
    expect(opcje.find((o) => o.value === biezacy).label).toContain('Bieżący tydzień')
    expect(opcje.find((o) => o.value === przyszly).label).toContain('Przyszły tydzień')
    // Tydzień -1 (poprzedni) jest tuż przed bieżącym w liście.
    const idxBiez = opcje.findIndex((o) => o.value === biezacy)
    expect(opcje[idxBiez - 1].label).toContain('Poprzedni tydzień')
  })
})
