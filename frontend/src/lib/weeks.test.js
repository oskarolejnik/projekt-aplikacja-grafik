import { describe, it, expect } from 'vitest'
import { generujOpcjeTygodni, generujOpcjeMiesiecy, generujOpcjeCyklu } from './weeks'

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

  it('bez argumentu startuje w środę (konwencja historyczna)', () => {
    // ISO date → UTC północ → getUTCDay niezależny od strefy; 3 = środa
    for (const o of opcje) expect(start(o.value).getUTCDay()).toBe(3)
  })

  it('poczatek_tygodnia z configu wyznacza dzień startu (0=pon … 6=nie)', () => {
    // config 0=poniedziałek → getUTCDay()=1; config 6=niedziela → getUTCDay()=0
    const mapowanie = [[0, 1], [2, 3], [5, 6], [6, 0]]
    for (const [cfg, js] of mapowanie) {
      const { opcje: o2 } = generujOpcjeTygodni(cfg)
      expect(o2).toHaveLength(8)
      for (const o of o2) {
        expect(start(o.value).getUTCDay()).toBe(js)
        expect((koniec(o.value) - start(o.value)) / DZIEN).toBe(6)
      }
    }
  })

  it('wartość spoza zakresu/nie-liczba wraca do środy', () => {
    for (const zly of [null, undefined, 'x', 9]) {
      const { opcje: o2 } = generujOpcjeTygodni(zly)
      // 9 → normalizacja modulo daje 2 (środa); nie-liczby → fallback środa
      expect(start(o2[0].value).getUTCDay()).toBe(3)
    }
  })
})

describe('generujOpcjeMiesiecy', () => {
  const { opcje, domyslny, biezacy, przyszly } = generujOpcjeMiesiecy()

  it('zwraca 8 miesięcy z poprawnym kształtem', () => {
    expect(opcje).toHaveLength(8)
    for (const o of opcje) {
      expect(o.value).toMatch(/^\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}$/)
      expect(o.label.length).toBeGreaterThan(0)
    }
  })

  it('każda opcja to pełny miesiąc kalendarzowy (1. → ostatni dzień)', () => {
    for (const o of opcje) {
      const [s, e] = o.value.split('|')
      expect(s.slice(8, 10)).toBe('01')                       // start = 1. dnia
      const [ry, rm] = e.split('-').map(Number)
      const ostatni = new Date(Date.UTC(ry, rm, 0)).getUTCDate()
      expect(Number(e.slice(8, 10))).toBe(ostatni)            // koniec = ostatni dzień
    }
  })

  it('bieżący = domyślny, tag „Bieżący miesiąc"', () => {
    expect(biezacy).toBe(domyslny)
    expect(opcje.find((o) => o.value === biezacy).label).toContain('Bieżący miesiąc')
    expect(opcje.find((o) => o.value === przyszly).label).toContain('Przyszły miesiąc')
  })
})

describe('generujOpcjeCyklu', () => {
  it('dyspozytor: tydzien vs miesiac', () => {
    const [ts, te] = generujOpcjeCyklu('tydzien', 2).biezacy.split('|')
    expect((new Date(te) - new Date(ts)) / DZIEN).toBe(6)     // tydzień = 6 dni różnicy
    const [ms] = generujOpcjeCyklu('miesiac').biezacy.split('|')
    expect(ms.slice(8, 10)).toBe('01')                        // miesiąc startuje 1.
    // domyślnie tydzień
    expect(generujOpcjeCyklu().biezacy.split('|')[0]).toBe(generujOpcjeTygodni(2).biezacy.split('|')[0])
  })
})
