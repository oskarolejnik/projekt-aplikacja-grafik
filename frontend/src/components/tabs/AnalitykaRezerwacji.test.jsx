// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../lib/icons', () => ({ Icon: ({ name }) => <span aria-hidden="true">{name}</span> }))

import AnalitykaRezerwacji from './AnalitykaRezerwacji'

const summary = {
  covery: { suma: 120, srednia_dzienna: 4, wg_dnia: [] },
  statusy: { no_show: 3, no_show_proc: 12, konwersja_proc: 88, odbyla: 22, aktywne: 4 },
  kanaly: [
    { kanal: 'online', liczba: 18, proc: 60 },
    { kanal: 'reczna', liczba: 12, proc: 40 },
  ],
  lead_time: { mediana_dni: 4, srednia_dni: 5 },
  wielkosc_grup: [],
  szczyty: {
    wg_dnia_tygodnia: [
      { dzien: 'Pon', covery: 10 }, { dzien: 'Wt', covery: 12 },
      { dzien: 'Śr', covery: 8 }, { dzien: 'Czw', covery: 15 },
      { dzien: 'Pt', covery: 28 }, { dzien: 'Sob', covery: 35 },
      { dzien: 'Nd', covery: 12 },
    ],
    wg_godziny: [],
  },
}

const occupancy = {
  agregat: {
    oblozenie_stolowe_proc: 48,
    oblozenie_miejscowe_proc: 42,
    covery: 120,
  },
  per_dzien: [],
}

const operational = {
  jakosc_danych: {
    zakonczone_wizyty: 25,
    z_pelnym_pomiarem: 20,
    bez_pomiaru: 3,
    nieprawidlowy_pomiar: 1,
    pominiete_przeniesienia: 1,
    kompletnosc_proc: 80,
  },
  turn_time: {
    proba: 20,
    mediana_min: 92,
    srednia_min: 96,
    planowana_mediana_min: 120,
    odchylenie_min: -28,
    wg_wielkosci_grupy: [
      { grupa: '1-2', proba: 8, mediana_min: 82, srednia_min: 84, planowana_mediana_min: 120, odchylenie_min: -38 },
      { grupa: '3-4', proba: 12, mediana_min: 104, srednia_min: 105, planowana_mediana_min: 120, odchylenie_min: -16 },
    ],
  },
  wykorzystanie: {
    sale: [{ sala_id: 1, nazwa: 'Sala główna', wizyty: 14, covery: 48, rzeczywiste_minuty: 1320, pomiary: 14 }],
    stoliki: [{ stolik_id: 4, nazwa: 'T4', sala_id: 1, sala_nazwa: 'Sala główna', wizyty: 7, covery: 22, rzeczywiste_minuty: 650, pomiary: 7 }],
    kombinacje: [{
      kombinacja_id: 9,
      wersja_id: 3,
      nazwa: 'T4 + T2',
      sala_id: 1,
      sala_nazwa: 'Sala główna',
      stoliki: [{ id: 4, nazwa: 'T4' }, { id: 2, nazwa: 'T2' }],
      wizyty: 3,
      covery: 18,
      rzeczywiste_minuty: 330,
      pomiary: 3,
    }],
    bez_przydzialu: { wizyty: 1, covery: 2, rzeczywiste_minuty: 75, pomiary: 1 },
  },
}

const demand = {
  okres: { start: '2026-06-20', end: '2026-07-19' },
  odrzucony_popyt: {
    proby: 12,
    osoby: 40,
    z_waitlista: 4,
    przyczyny: [
      { kod: 'brak_pojemnosci', etykieta: 'Brak pasującej konfiguracji', proby: 7, osoby: 26 },
      { kod: 'limit_osob', etykieta: 'Limit nowych osób', proby: 5, osoby: 14 },
    ],
    wg_godziny: [
      { godzina: '19:00', proby: 8, osoby: 30 },
      { godzina: '20:00', proby: 4, osoby: 10 },
    ],
    wg_wielkosci_grupy: [
      { grupa: '1-2', proby: 4, osoby: 8 },
      { grupa: '5-6', proby: 8, osoby: 32 },
    ],
    kanaly: [],
    wg_zasobu: [],
  },
  waitlista: {
    wpisy: 10,
    zaoferowano: 8,
    zaakceptowano: 7,
    odbyte: 5,
    zaoferowano_proc: 80,
    zaakceptowano_proc: 70,
    odbyte_proc: 50,
    mediana_do_oferty_min: 18,
  },
  jakosc_danych: {
    sledzenie_od: '2026-07-01',
    wpisy_bez_zdarzenia: 1,
    historyczne_bez_przyczyny: 2,
    zaakceptowane_bez_potwierdzonej_wizyty: 2,
  },
}

const responseFor = (path) => {
  if (path.startsWith('/analityka/rezerwacje/popyt?')) return demand
  if (path.startsWith('/analityka/rezerwacje/operacyjna?')) return operational
  if (path.startsWith('/analityka/oblozenie?')) return occupancy
  if (path.startsWith('/analityka/rezerwacje?')) return summary
  throw new Error(`Nieoczekiwane żądanie: ${path}`)
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  apiMock.mockReset()
  apiMock.mockImplementation((path) => Promise.resolve(responseFor(path)))
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('AnalitykaRezerwacji R7', () => {
  it('pobiera cztery anonimowe źródła równolegle i pokazuje spokojny przegląd', async () => {
    render(<AnalitykaRezerwacji />)

    expect(await screen.findByText('120')).toBeInTheDocument()
    expect(screen.getByText('Zarezerwowane osoby')).toBeInTheDocument()
    expect(screen.getByText('Planowane obłożenie stołów')).toBeInTheDocument()
    expect(screen.getByText('20/25')).toBeInTheDocument()
    expect(screen.getByText('1 h 32 min')).toBeInTheDocument()
    expect(screen.getByText('48%')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledTimes(4)
    expect(apiMock.mock.calls.map(([path]) => path)).toEqual(expect.arrayContaining([
      expect.stringMatching(/^\/analityka\/rezerwacje\?start=/),
      expect.stringMatching(/^\/analityka\/oblozenie\?start=/),
      expect.stringMatching(/^\/analityka\/rezerwacje\/operacyjna\?start=/),
      expect.stringMatching(/^\/analityka\/rezerwacje\/popyt\?start=/),
    ]))
    apiMock.mock.calls.forEach(([, method, body, options]) => {
      expect(method).toBe('GET')
      expect(body).toBeNull()
      expect(options.signal).toBeInstanceOf(AbortSignal)
    })
    expect(screen.getByText(/Lokalo nie zmienia czasu wizyt ani zasad dostępności automatycznie/)).toBeInTheDocument()
  })

  it('pokazuje utracony popyt i skuteczność waitlisty bez PII ani automatycznej rekomendacji', async () => {
    render(<AnalitykaRezerwacji />)
    await screen.findByText('Najważniejsze fakty')

    fireEvent.click(screen.getByRole('button', { name: 'Popyt i waitlista' }))

    expect(screen.getByText('Popyt i lista oczekujących')).toBeInTheDocument()
    expect(screen.getByText('Próby bez terminu').parentElement).toHaveTextContent('12')
    expect(screen.getByText('Osoby w tych próbach').parentElement).toHaveTextContent('40')
    expect(screen.getByText('Wizyty z waitlisty').parentElement).toHaveTextContent('50%')
    expect(screen.getByText('Wizyty z waitlisty').parentElement).toHaveTextContent('5 z 10 wpisów')
    expect(screen.getByText('Brak pasującej konfiguracji')).toBeInTheDocument()
    expect(screen.getByText(/Pomiar odrzuconych prób działa od 2026-07-01/)).toBeInTheDocument()
    expect(screen.queryByText(/Nowak|Kowalska|jan@example|500 600/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Zastosuj|Zmień regułę/i })).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Przekrój'), { target: { value: 'hours' } })
    expect(screen.getByText('19:00')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Przekrój'), { target: { value: 'groups' } })
    expect(screen.getByText('5-6 os.')).toBeInTheDocument()
  })

  it('odróżnia prawidłowe zero od braku mianownika konwersji', async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/analityka/rezerwacje/popyt?')) {
        return Promise.resolve({
          ...demand,
          odrzucony_popyt: {
            proby: 0,
            osoby: 0,
            z_waitlista: 0,
            przyczyny: [],
            wg_godziny: [],
            wg_wielkosci_grupy: [],
            kanaly: [],
            wg_zasobu: [],
          },
          waitlista: {
            wpisy: 0,
            zaoferowano: 0,
            zaakceptowano: 0,
            odbyte: 0,
            zaoferowano_proc: null,
            zaakceptowano_proc: null,
            odbyte_proc: null,
            mediana_do_oferty_min: null,
          },
          jakosc_danych: {
            sledzenie_od: '2026-06-01',
            wpisy_bez_zdarzenia: 0,
            historyczne_bez_przyczyny: 0,
            zaakceptowane_bez_potwierdzonej_wizyty: 0,
          },
        })
      }
      return Promise.resolve(responseFor(path))
    })

    render(<AnalitykaRezerwacji />)
    await screen.findByText('Najważniejsze fakty')
    fireEvent.click(screen.getByRole('button', { name: 'Popyt i waitlista' }))

    expect(screen.getByText('Próby bez terminu').parentElement).toHaveTextContent('0')
    expect(screen.getByText('Wizyty z waitlisty').parentElement).toHaveTextContent('—')
    expect(screen.getByText('Wizyty z waitlisty').parentElement).not.toHaveTextContent('0%')
    expect(screen.getByText('W tym okresie nie odnotowano prób bez dostępnego terminu.')).toBeInTheDocument()
    expect(screen.getByText('W tym okresie nie było wpisów na liście oczekujących.')).toBeInTheDocument()
  })

  it('pokazuje brak pomiaru i planu jako kreskę, nigdy jako zero minut', async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/analityka/rezerwacje/operacyjna?')) {
        return Promise.resolve({
          jakosc_danych: {
            zakonczone_wizyty: 0,
            z_pelnym_pomiarem: 0,
            bez_pomiaru: 0,
            nieprawidlowy_pomiar: 0,
            pominiete_przeniesienia: 0,
            kompletnosc_proc: 0,
          },
          turn_time: {
            proba: 0,
            mediana_min: null,
            srednia_min: null,
            planowana_mediana_min: null,
            odchylenie_min: null,
            wg_wielkosci_grupy: [],
          },
          wykorzystanie: { sale: [], stoliki: [], kombinacje: [], bez_przydzialu: {} },
        })
      }
      return Promise.resolve(responseFor(path))
    })

    render(<AnalitykaRezerwacji />)

    const metric = (await screen.findByText('Mediana wizyty')).parentElement
    expect(metric).toHaveTextContent('—')
    expect(metric).toHaveTextContent('plan —')
    expect(metric).not.toHaveTextContent('0 min')

    fireEvent.click(screen.getByRole('button', { name: 'Czas wizyt' }))
    expect(screen.getByText('Brak pełnych pomiarów w tym okresie.')).toBeInTheDocument()
    expect(screen.queryByText(/Kompletność próby wynosi 0%/)).not.toBeInTheDocument()
  })

  it('pokazuje faktyczny czas według grup i nie interpretuje braku próby jako rekomendacji', async () => {
    render(<AnalitykaRezerwacji />)
    await screen.findByText('Najważniejsze fakty')

    fireEvent.click(screen.getByRole('button', { name: 'Czas wizyt' }))

    expect(screen.getAllByText('1-2 os.').length).toBeGreaterThan(0)
    expect(screen.getAllByText('1 h 22 min').length).toBeGreaterThan(0)
    expect(screen.getAllByText('38 min krócej').length).toBeGreaterThan(0)
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Zastosuj|Zmień regułę/i })).not.toBeInTheDocument()
  })

  it('przełącza sale, stoły i historyczne konfiguracje bez poziomej tabeli na mobile', async () => {
    render(<AnalitykaRezerwacji />)
    await screen.findByText('Najważniejsze fakty')
    fireEvent.click(screen.getByRole('button', { name: 'Sale i stoły' }))

    expect(screen.getByText('Sala główna')).toBeInTheDocument()
    expect(screen.getByText('22 h')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Zasób'), { target: { value: 'stoliki' } })
    expect(screen.getByText('T4')).toBeInTheDocument()
    expect(screen.getByText('10 h 50 min')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Zasób'), { target: { value: 'kombinacje' } })
    expect(screen.getByText('T4 + T2')).toBeInTheDocument()
    expect(screen.getByText(/Sala główna · T4 \+ T2/, { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByText(/1 wizyt nie ma historycznego przydziału/)).toBeInTheDocument()
  })

  it('zachowuje wyniki podczas odświeżania tego samego okresu i aktualizuje je atomowo', async () => {
    render(<AnalitykaRezerwacji />)
    await screen.findByText('120')

    const nextSummary = deferred()
    const nextOccupancy = deferred()
    const nextOperational = deferred()
    const nextDemand = deferred()
    apiMock
      .mockImplementationOnce(() => nextSummary.promise)
      .mockImplementationOnce(() => nextOccupancy.promise)
      .mockImplementationOnce(() => nextOperational.promise)
      .mockImplementationOnce(() => nextDemand.promise)

    fireEvent.click(screen.getByRole('button', { name: 'Odśwież' }))

    expect(screen.getByText('120')).toBeInTheDocument()
    expect(await screen.findByText('Poprzednie wyniki pozostają widoczne.')).toBeInTheDocument()

    await act(async () => {
      nextSummary.resolve({ ...summary, covery: { ...summary.covery, suma: 144 } })
      nextOccupancy.resolve(occupancy)
      nextOperational.resolve(operational)
      nextDemand.resolve(demand)
    })

    expect(await screen.findByText('144')).toBeInTheDocument()
    expect(screen.queryByText('Poprzednie wyniki pozostają widoczne.')).not.toBeInTheDocument()
  })

  it('przy awarii źródła popytu zachowuje poprzedni poprawny fragment zamiast zera', async () => {
    render(<AnalitykaRezerwacji />)
    await screen.findByText('120')

    const nextSummary = deferred()
    const nextOccupancy = deferred()
    const nextOperational = deferred()
    const nextDemand = deferred()
    apiMock
      .mockImplementationOnce(() => nextSummary.promise)
      .mockImplementationOnce(() => nextOccupancy.promise)
      .mockImplementationOnce(() => nextOperational.promise)
      .mockImplementationOnce(() => nextDemand.promise)

    fireEvent.click(screen.getByRole('button', { name: 'Odśwież' }))
    await act(async () => {
      nextSummary.resolve({ ...summary, covery: { ...summary.covery, suma: 144 } })
      nextOccupancy.resolve({
        ...occupancy,
        agregat: { ...occupancy.agregat, oblozenie_stolowe_proc: 61 },
      })
      nextOperational.resolve(operational)
      nextDemand.reject(new Error('Popyt niedostępny'))
    })

    expect(await screen.findByText('144')).toBeInTheDocument()
    expect(screen.getByText('61%')).toBeInTheDocument()
    expect(screen.getByText(/Nie udało się odświeżyć: utraconego popytu i waitlisty/)).toBeInTheDocument()
    expect(screen.getByText(/Częściowa aktualizacja/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Popyt i waitlista' }))
    expect(screen.getByText('Wizyty z waitlisty').parentElement).toHaveTextContent('50%')
  })

  it('abortuje poprzedni okres i odrzuca jego spóźnione odpowiedzi', async () => {
    const first = [deferred(), deferred(), deferred(), deferred()]
    first.forEach((request) => apiMock.mockImplementationOnce(() => request.promise))
    render(<AnalitykaRezerwacji />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(4))
    const firstSignals = apiMock.mock.calls.slice(0, 4).map((call) => call[3].signal)

    fireEvent.click(screen.getByRole('button', { name: 'Własny' }))
    fireEvent.change(screen.getByLabelText('Od'), { target: { value: '2026-06-01' } })
    fireEvent.change(screen.getByLabelText('Do'), { target: { value: '2026-06-30' } })

    await waitFor(() => expect(apiMock.mock.calls.length).toBeGreaterThanOrEqual(8))
    firstSignals.forEach((signal) => expect(signal.aborted).toBe(true))

    await act(async () => {
      first[0].resolve({ ...summary, covery: { ...summary.covery, suma: 999 } })
      first[1].resolve(occupancy)
      first[2].resolve(operational)
      first[3].resolve(demand)
    })

    expect(screen.queryByText('999')).not.toBeInTheDocument()
  })

  it('pokazuje lokalny błąd i pozwala ponowić bez globalnego toastu', async () => {
    apiMock.mockRejectedValue(new Error('Analityka jest chwilowo niedostępna.'))
    render(<AnalitykaRezerwacji />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Analityka jest chwilowo niedostępna.')
    expect(screen.queryByText('Najważniejsze fakty')).not.toBeInTheDocument()

    apiMock.mockImplementation((path) => Promise.resolve(responseFor(path)))
    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))

    expect(await screen.findByText('Najważniejsze fakty')).toBeInTheDocument()
  })

  it('pokazuje pusty stan, gdy backend zwraca wyłącznie grupy bez próby', async () => {
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/analityka/rezerwacje/operacyjna?')) {
        return Promise.resolve({
          ...operational,
          turn_time: {
            ...operational.turn_time,
            wg_wielkosci_grupy: [
              { grupa: '1-2', proba: 0 },
              { grupa: '3-4', proba: 0 },
              { grupa: '5-6', proba: 0 },
              { grupa: '7+', proba: 0 },
            ],
          },
        })
      }
      return Promise.resolve(responseFor(path))
    })

    render(<AnalitykaRezerwacji />)
    await screen.findByText('Najważniejsze fakty')
    fireEvent.click(screen.getByRole('button', { name: 'Czas wizyt' }))

    expect(screen.getByText('Brak pełnych pomiarów w tym okresie.')).toBeInTheDocument()
    expect(screen.queryByText('1-2 os.')).not.toBeInTheDocument()
  })
})
