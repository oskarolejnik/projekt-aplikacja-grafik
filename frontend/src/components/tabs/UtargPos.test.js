import { describe, it, expect } from 'vitest'
import { parsujCsvUtargu } from './UtargPos'

describe('parsujCsvUtargu', () => {
  it('parsuje średnikowy CSV z nagłówkiem i polskimi przecinkami', () => {
    const csv = 'data;netto;gotowka;karta;rachunki\n2026-07-01;4250,50;1200;3050,50;85\n2026-07-02;3100;;;\n'
    const { dni, bledy } = parsujCsvUtargu(csv)
    expect(bledy).toHaveLength(0)
    expect(dni).toEqual([
      { data: '2026-07-01', netto: 4250.5, gotowka: 1200, karta: 3050.5, liczba_rachunkow: 85 },
      { data: '2026-07-02', netto: 3100, gotowka: null, karta: null, liczba_rachunkow: null },
    ])
  })

  it('parsuje przecinkowy CSV bez nagłówka', () => {
    const { dni } = parsujCsvUtargu('2026-07-03,1500.25,500,1000.25,40')
    expect(dni).toEqual([
      { data: '2026-07-03', netto: 1500.25, gotowka: 500, karta: 1000.25, liczba_rachunkow: 40 },
    ])
  })

  it('zgłasza błędne wiersze (poza nagłówkiem), nie wywala całości', () => {
    const { dni, bledy } = parsujCsvUtargu('naglowek;x\n2026-07-01;100\nzepsuty;wiersz\n2026-07-02;200')
    expect(dni.map((d) => d.data)).toEqual(['2026-07-01', '2026-07-02'])
    expect(bledy).toHaveLength(1)
    expect(bledy[0]).toContain('wiersz 3')
  })

  it('pusty plik → zero dni', () => {
    expect(parsujCsvUtargu('').dni).toHaveLength(0)
  })
})
