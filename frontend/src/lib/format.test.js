import { describe, it, expect } from 'vitest'
import { ddmmyyyy, hhmm, godzinyHM, zl, tloKoloru, kolorStanowiska, zakresDni } from './format'

describe('ddmmyyyy', () => {
  it('zamienia ISO na DD.MM.YYYY', () => {
    expect(ddmmyyyy('2026-06-01')).toBe('01.06.2026')
  })
  it('pusty wejściowy → pusty', () => {
    expect(ddmmyyyy('')).toBe('')
    expect(ddmmyyyy(null)).toBe('')
  })
})

describe('hhmm', () => {
  it('przycina sekundy', () => {
    expect(hhmm('08:00:00')).toBe('08:00')
    expect(hhmm('23:15')).toBe('23:15')
  })
  it('puste/null → pusty', () => {
    expect(hhmm('')).toBe('')
    expect(hhmm(null)).toBe('')
  })
})

describe('godzinyHM', () => {
  it('godziny dziesiętne → HH:MM', () => {
    expect(godzinyHM(8.5)).toBe('08:30')
    expect(godzinyHM(1.25)).toBe('01:15')
    expect(godzinyHM(0)).toBe('00:00')
    expect(godzinyHM(160)).toBe('160:00')  // bez ograniczenia do 24h
  })
  it('ujemne/niepoprawne → 00:00', () => {
    expect(godzinyHM(-5)).toBe('00:00')
    expect(godzinyHM('abc')).toBe('00:00')
  })
})

describe('zl', () => {
  it('formatuje kwotę w PLN (2 miejsca) z symbolem zł', () => {
    const out = zl(240)
    expect(out).toContain('240,00')
    expect(out).toContain('zł')
  })
  it('niepoprawne → 0,00 zł', () => {
    expect(zl('x')).toContain('0,00')
  })
})

describe('tloKoloru', () => {
  it('miesza kolor z ciemną bazą (rgb)', () => {
    expect(tloKoloru('#ffffff')).toBe('rgb(84, 84, 84)')  // 255*0.28 + 18*0.72 = 84
  })
  it('niepoprawny hex → undefined', () => {
    expect(tloKoloru('')).toBeUndefined()
    expect(tloKoloru('#fff')).toBeUndefined()   // za krótki
    expect(tloKoloru('xyz')).toBeUndefined()
  })
})

describe('kolorStanowiska', () => {
  it('deterministyczny (ta sama nazwa → ten sam kolor z palety)', () => {
    const a = kolorStanowiska('sala')
    expect(a).toBe(kolorStanowiska('sala'))
    expect(a).toMatch(/^#[0-9a-f]{6}$/i)
  })
})

describe('zakresDni', () => {
  it('lista kolejnych dni włącznie', () => {
    expect(zakresDni('2026-06-01', '2026-06-03')).toEqual(['2026-06-01', '2026-06-02', '2026-06-03'])
  })
  it('ten sam start i koniec → jeden dzień', () => {
    expect(zakresDni('2026-06-10', '2026-06-10')).toEqual(['2026-06-10'])
  })
})
