import { describe, it, expect } from 'vitest'
import { TYPY, KLUCZE_MODULOW, znormalizujModuly, PRESET_INNY } from './typy'

describe('typy — taksonomia lokali gastro', () => {
  it('ma 14 typów, każdy z kompletnym presetem 6 flag, ikoną i opisem', () => {
    expect(TYPY).toHaveLength(14)
    for (const t of TYPY) {
      expect(t.id).toBeTruthy()
      expect(t.nazwa).toBeTruthy()
      expect(t.ikona).toBeTruthy()
      expect(t.opis).toBeTruthy()
      for (const k of KLUCZE_MODULOW) expect(typeof t.moduly[k]).toBe('boolean')
    }
  })

  it('ma dokładnie 3 typy „popularny" (pizzeria, à la carte, karczma)', () => {
    expect(TYPY.filter((t) => t.popularny).map((t) => t.id))
      .toEqual(['pizzeria', 'restauracja-a-la-carte', 'karczma-regionalna'])
  })

  it('każdy preset spełnia zależność: online ⇒ rezerwacje', () => {
    for (const t of [...TYPY, { moduly: PRESET_INNY }]) {
      if (t.moduly.rezerwacje_online) expect(t.moduly.modul_rezerwacje).toBe(true)
    }
  })

  it('presety są zróżnicowane (nie wszystkie takie same)', () => {
    const podpisy = new Set(TYPY.map((t) => KLUCZE_MODULOW.map((k) => (t.moduly[k] ? '1' : '0')).join('')))
    expect(podpisy.size).toBeGreaterThanOrEqual(6)
  })

  it('znormalizujModuly wymusza online ⇒ rezerwacje', () => {
    expect(znormalizujModuly({ rezerwacje_online: true, modul_rezerwacje: false }).modul_rezerwacje).toBe(true)
    expect(znormalizujModuly({ rezerwacje_online: false, modul_rezerwacje: false }).rezerwacje_online).toBe(false)
  })
})
