// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { warsawDateISO } from '../../lib/date'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import Pulpit from './Pulpit'

const DANE = {
  przychod: { razem: 1000, srednia_dzienna: 100, gotowka: 300, karta: 600, przelew: 100, impreza: 0, dzienny: [] },
  rozchod: { razem: 200 },
  saldo_kasy: 800,
  ruch: { rachunki: 42, srednia_dzienna: 4 },
  rezerwacje: { razem: 6, goscie: 18, wg_statusu: {} },
  koszt_pracy_miesiac: { miesiac: 7, rok: 2026, kwota: 300 },
  alerty_kasowe: { dni_z_anomalia: 0, suma_braki: 0 },
  wynik: 500,
}

const odpowiedz = (path) => {
  if (!path) return Promise.resolve({})
  if (path === '/lokal/config') return Promise.resolve({ impreza_osobne_rozliczenie: false })
  if (path.startsWith('/pulpit?')) return Promise.resolve(DANE)
  if (path.startsWith('/alerty-kasowe?')) return Promise.resolve({ alerty: [] })
  if (path === '/alerty-obsady?dni=14') return Promise.resolve({ alerty: [], dni: 14, razem_brakuje: 0 })
  return Promise.resolve({})
}

describe('Pulpit perceived loading', () => {
  beforeEach(() => apiMock.mockImplementation(odpowiedz))
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('wyznacza dzień operacyjny w strefie Europe/Warsaw zamiast według UTC', () => {
    expect(warsawDateISO(new Date('2026-07-10T22:30:00.000Z'))).toBe('2026-07-11')
  })

  it('pokazuje stabilny szkielet przy pierwszym ładowaniu i potem dane', async () => {
    let resolvePulpit
    apiMock.mockImplementation((path) => {
      if (path?.startsWith('/pulpit?')) return new Promise((resolve) => { resolvePulpit = resolve })
      return odpowiedz(path)
    })

    render(<Pulpit />)
    expect(screen.getByRole('status', { name: 'Wczytywanie pulpitu' })).toBeInTheDocument()

    await act(async () => resolvePulpit(DANE))
    expect(await screen.findByText(/1.?000,00 zł/)).toBeInTheDocument()
  })

  it('zachowuje poprzednie KPI podczas odświeżania zakresu', async () => {
    let resolveRefresh
    let pulpitCalls = 0
    apiMock.mockImplementation((path) => {
      if (path?.startsWith('/pulpit?')) {
        pulpitCalls += 1
        if (pulpitCalls === 1) return Promise.resolve(DANE)
        return new Promise((resolve) => { resolveRefresh = resolve })
      }
      return odpowiedz(path)
    })

    render(<Pulpit />)
    expect(await screen.findByText(/1.?000,00 zł/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Początek okresu'), { target: { value: '2026-07-01' } })
    expect(await screen.findByText('Aktualizuję dane…')).toBeInTheDocument()
    expect(screen.getByText(/1.?000,00 zł/)).toBeInTheDocument()

    await act(async () => resolveRefresh({
      ...DANE,
      przychod: { ...DANE.przychod, razem: 1250 },
    }))
    expect(await screen.findByText(/1.?250,00 zł/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('Aktualizuję dane…')).not.toBeInTheDocument())
  })

  it('nie blokuje KPI, gdy pomocnicze alerty są niedostępne', async () => {
    apiMock.mockImplementation((path) => {
      if (path?.startsWith('/alerty-kasowe?') || path === '/alerty-obsady?dni=14') {
        return Promise.reject(new Error('offline'))
      }
      return odpowiedz(path)
    })

    render(<Pulpit />)
    expect(await screen.findByText(/1.?000,00 zł/)).toBeInTheDocument()
    expect(screen.getByText(/Główne KPI są aktualne/)).toBeInTheDocument()
    expect(screen.getByText('Niepełne dane')).toBeInTheDocument()
    expect(screen.queryByText('Na teraz wszystko jest pod kontrolą.')).not.toBeInTheDocument()
  })

  it('nie miesza alertów z poprzedniego zakresu z nowymi KPI', async () => {
    let pulpitCalls = 0
    apiMock.mockImplementation((path) => {
      if (path?.startsWith('/pulpit?')) {
        pulpitCalls += 1
        return Promise.resolve(pulpitCalls === 1 ? DANE : {
          ...DANE,
          przychod: { ...DANE.przychod, razem: 1250 },
        })
      }
      if (path?.startsWith('/alerty-kasowe?')) {
        return pulpitCalls === 1
          ? Promise.resolve({ alerty: [{ data: '2026-06-12', status: 'brak', problemy: [{ typ: 'kasa', roznica: -50 }] }] })
          : Promise.reject(new Error('offline'))
      }
      return odpowiedz(path)
    })

    render(<Pulpit />)
    expect(await screen.findByText('2026-06-12')).toBeInTheDocument()
    expect(screen.getByText('Kasa · wybrany okres')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Początek okresu'), { target: { value: '2026-07-01' } })

    expect(await screen.findByText(/1.?250,00 zł/)).toBeInTheDocument()
    expect(screen.queryByText('2026-06-12')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Niedostępne sekcje zostały ukryte')
  })

  it('nie miesza alertów z nowego zakresu ze starymi KPI po błędzie głównego odświeżenia', async () => {
    let pulpitCalls = 0
    apiMock.mockImplementation((path) => {
      if (path?.startsWith('/pulpit?')) {
        pulpitCalls += 1
        return pulpitCalls === 1 ? Promise.resolve(DANE) : Promise.reject(new Error('offline'))
      }
      if (path?.startsWith('/alerty-kasowe?')) {
        const data = pulpitCalls === 1 ? '2026-06-12' : '2026-07-01'
        return Promise.resolve({ alerty: [{ data, status: 'brak', problemy: [{ typ: 'kasa', roznica: -50 }] }] })
      }
      return odpowiedz(path)
    })

    render(<Pulpit />)
    expect(await screen.findByText('2026-06-12')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Początek okresu'), { target: { value: '2026-07-01' } })

    expect(await screen.findByText(/Pokazujemy ostatnie dostępne dane/)).toBeInTheDocument()
    expect(screen.getByText('2026-06-12')).toBeInTheDocument()
    expect(screen.queryByText('2026-07-01')).not.toBeInTheDocument()
    expect(screen.getByText(/1.?000,00 zł/)).toBeInTheDocument()
  })

  it('udostępnia wartości wykresu również bez hovera', async () => {
    apiMock.mockImplementation((path) => {
      if (path?.startsWith('/pulpit?')) return Promise.resolve({
        ...DANE,
        przychod: {
          ...DANE.przychod,
          dzienny: [
            { data: '2026-07-09', przychod: 83.2 },
            { data: '2026-07-10', przychod: 137.4 },
          ],
        },
      })
      return odpowiedz(path)
    })

    render(<Pulpit />)
    fireEvent.click(await screen.findByText('Pokaż wartości dzienne'))

    const values = screen.getByRole('list', { name: 'Wartości przychodu według dni' })
    expect(within(values).getByText('09.07')).toBeInTheDocument()
    expect(within(values).getByText(/137,40 zł/)).toBeInTheDocument()
  })
})
