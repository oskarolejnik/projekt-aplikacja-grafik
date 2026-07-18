// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getApiBase: () => 'https://lokal.example' }))
import {
  HOST_SNAPSHOT_CACHE_TTL_MS,
  readHostSnapshotCache,
  writeHostSnapshotCache,
} from './hostSnapshotCache'
import {
  clearReservationSessions,
  rotateReservationPrivacyEpoch,
} from './reservationSession'

const USER = { id: 41, login: 'recepcja' }
const DAY = '2026-07-18'
const GENERATED_AT = '2026-07-18T16:00:00.000Z'

const snapshot = (day = DAY) => ({
  version: GENERATED_AT,
  schema_version: 1,
  data: day,
  generated_at: GENERATED_AT,
  kolejka: {
    data: day,
    nadchodzace: [{
      id: 11,
      data: day,
      godz_od: '18:00',
      godz_do: '20:00',
      liczba_osob: 4,
      stolik_id: 3,
      stoliki_dodatkowe: [4],
      status: 'potwierdzona',
      faza_hosta: 'przybyl',
      nazwisko: 'Kowalska-PII',
      telefon: '500-PII-600',
      email: 'pii@example.test',
      notatka: 'NOTATKA-PII',
      alergie: 'ALERGIA-PII',
      tagi: ['TAG-PII'],
      okazja_typ: 'OKAZJA-PII',
      gosc: {
        alergie: 'ORZECHY-PII',
        tagi: ['VIP-PII'],
        okazja_typ: 'URODZINY-PII',
      },
    }],
    na_sali: [],
    zakonczone: [],
    waitlista: [{
      id: 51,
      godz_od: '19:00',
      liczba_osob: 2,
      status: 'oczekuje',
      nazwisko: 'Nowak-WAITLIST-PII',
      telefon: '700-WAITLIST-PII',
      notatka: 'WAITLIST-NOTE-PII',
    }],
    komunikacja_waitlist: [{
      id: 52,
      status: 'anulowano',
      nazwisko: 'Terminal-WAITLIST-PII',
      telefon: '711-TERMINAL-PII',
      communication_summary: {
        state: 'uncertain',
        channel: 'sms',
        attention_count: 1,
        attention_required: true,
        recipient: '711-SUMMARY-PII',
      },
    }],
  },
  os_czasu: {
    data: day,
    stoly: [{ id: 3, nazwa: 'Stół 3', sekcja: 'Okno', strefa: 'Sala' }],
    godziny: ['18:00', '18:30'],
    zajetosci: [{
      stolik_id: 3,
      godz_od: '18:00',
      godz_do: '20:00',
      rezerwacja_id: 11,
      liczba_osob: 4,
      faza_hosta: 'przybyl',
      nazwisko: 'Timeline-PII',
      email: 'timeline@example.test',
      gosc: { alergie: 'TIMELINE-ALLERGY-PII' },
    }],
  },
  plan_sali: {
    data: day,
    sala_id: 1,
    sale: [{ id: 1, nazwa: 'Sala główna', aktywna: true, kolejnosc: 1 }],
    strefy: ['Sala'],
    stoliki: [{
      id: 3,
      nazwa: 'Stół 3',
      sala_id: 1,
      strefa: 'Sala',
      sekcja: 'Okno',
      kolejnosc: 1,
      pojemnosc: 4,
      pojemnosc_min: 2,
      ksztalt: 'prostokat',
      cechy: ['TABLE-TAG-PII'],
      aktywny: true,
      aktywny_w_planie: true,
      plan_x: 12,
      plan_y: 20,
      szerokosc: 18,
      wysokosc: 12,
      obrot: 0,
      rewir_nr: 7,
      status: 'potwierdzony',
      live: { otwarte: 1, zajete: true, aktualizacja: GENERATED_AT },
      rezerwacje: [{
        id: 11,
        data: day,
        godz_od: '18:00',
        godz_do: '20:00',
        liczba_osob: 4,
        status: 'potwierdzona',
        faza_hosta: 'przybyl',
        nazwisko: 'Plan-PII',
        telefon: '800-PLAN-PII',
        email: 'plan@example.test',
        notatka: 'PLAN-NOTE-PII',
        gosc: { tagi: ['PLAN-TAG-PII'] },
      }],
    }],
    kombinacje: [{
      id: 8,
      nazwa: 'Stół 3 + 4',
      stoliki: [3, 4],
      pojemnosc_min: 4,
      pojemnosc_max: 8,
      priorytet: 1,
      kanal: 'oba',
    }],
    secret: 'ROOT-PII',
  },
})

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  vi.useRealTimers()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('hostSnapshotCache', () => {
  it('zapisuje wyłącznie jawnie dozwolony, zanonimizowany snapshot i poprawnie go odczytuje', () => {
    expect(writeHostSnapshotCache(USER, snapshot())).toBe(true)

    const raw = JSON.stringify(sessionStorage)
    for (const pii of [
      'Kowalska-PII',
      '500-PII-600',
      'pii@example.test',
      'NOTATKA-PII',
      'ALERGIA-PII',
      'TAG-PII',
      'OKAZJA-PII',
      'Nowak-WAITLIST-PII',
      'Terminal-WAITLIST-PII',
      '711-TERMINAL-PII',
      '711-SUMMARY-PII',
      'Timeline-PII',
      'Plan-PII',
      'ROOT-PII',
      'TABLE-TAG-PII',
    ]) expect(raw).not.toContain(pii)
    for (const forbiddenField of ['telefon', 'email', 'notatka', 'alergie', 'tagi', 'okazja']) {
      expect(raw).not.toContain(`\\"${forbiddenField}`)
    }

    const cached = readHostSnapshotCache(USER, DAY)
    expect(cached).toMatchObject({
      data: DAY,
      schema_version: 1,
      kolejka: {
        nadchodzace: [{ id: 11, nazwisko: 'Gość', gosc: null }],
        waitlista: [{ id: 51, nazwisko: 'Gość', gosc: null }],
        komunikacja_waitlist: [{
          id: 52,
          status: 'anulowano',
          nazwisko: 'Gość',
          gosc: null,
          communication_summary: {
            state: 'uncertain',
            channel: 'sms',
            attention_count: 1,
            attention_required: true,
          },
        }],
      },
      os_czasu: {
        zajetosci: [{ rezerwacja_id: 11, nazwisko: 'Gość', gosc: null }],
      },
      plan_sali: {
        stoliki: [{ id: 3, status: 'potwierdzony', live: { zajete: true } }],
      },
    })
    expect(cached.plan_sali.stoliki[0].rezerwacje[0]).toEqual({
      id: 11,
      data: DAY,
      godz_od: '18:00',
      godz_do: '20:00',
      liczba_osob: 4,
      status: 'potwierdzona',
      faza_hosta: 'przybyl',
    })
  })

  it('zachowuje operacyjny hold oferty i jej pasek timeline bez danych kontaktowych', () => {
    const source = snapshot()
    source.kolejka.waitlista[0] = {
      ...source.kolejka.waitlista[0],
      data: DAY,
      status: 'zaoferowano',
      priorytet: 1,
      utworzono_at: '2026-07-18T15:30:00.000Z',
      zaoferowano_at: '2026-07-18T16:00:00.000Z',
      hold_stolik_id: 3,
      hold_stoliki_dodatkowe: [4],
      hold_godz_od: '19:00',
      hold_godz_do: '20:30',
      hold_do: '2026-07-18T16:10:00.000Z',
      offer_version: 4,
      communication_summary: {
        state: 'queued',
        channel: 'sms',
        attention_count: 0,
        attention_required: false,
        recipient: '500-COMMUNICATION-PII',
      },
    }
    source.os_czasu.zajetosci.push({
      typ: 'oferta',
      waitlist_id: 51,
      rezerwacja_id: null,
      stolik_id: 3,
      godz_od: '19:00',
      godz_do: '20:30',
      hold_do: '2026-07-18T16:10:00.000Z',
      liczba_osob: 2,
      nazwisko: 'Oferta-WAITLIST-PII',
    })

    expect(writeHostSnapshotCache(USER, source)).toBe(true)
    const raw = JSON.stringify(sessionStorage)
    expect(raw).not.toContain('500-COMMUNICATION-PII')
    expect(raw).not.toContain('Oferta-WAITLIST-PII')

    const cached = readHostSnapshotCache(USER, DAY)
    expect(cached.kolejka.waitlista[0]).toMatchObject({
      id: 51,
      status: 'zaoferowano',
      priorytet: 1,
      hold_stolik_id: 3,
      hold_stoliki_dodatkowe: [4],
      hold_godz_od: '19:00',
      hold_godz_do: '20:30',
      hold_do: '2026-07-18T16:10:00.000Z',
      offer_version: 4,
      nazwisko: 'Gość',
      communication_summary: {
        state: 'queued',
        channel: 'sms',
        attention_count: 0,
        attention_required: false,
      },
    })
    expect(cached.os_czasu.zajetosci).toContainEqual(expect.objectContaining({
      typ: 'oferta',
      waitlist_id: 51,
      rezerwacja_id: null,
      stolik_id: 3,
      godz_od: '19:00',
      godz_do: '20:30',
      nazwisko: 'Gość',
    }))
  })

  it('przechowuje tylko ostatni dzień aktora, ale nie niszczy go przy podglądzie innej daty', () => {
    expect(writeHostSnapshotCache(USER, snapshot('2026-07-19'))).toBe(true)
    expect(Object.keys(sessionStorage)).toHaveLength(1)

    expect(readHostSnapshotCache(USER, DAY)).toBeNull()
    expect(Object.keys(sessionStorage)).toHaveLength(1)
    expect(readHostSnapshotCache(USER, '2026-07-19')).toMatchObject({ data: '2026-07-19' })
  })

  it('usuwa snapshot po upływie TTL', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T16:00:00.000Z'))
    expect(writeHostSnapshotCache(USER, snapshot())).toBe(true)

    vi.setSystemTime(new Date(Date.now() + HOST_SNAPSHOT_CACHE_TTL_MS + 1))
    expect(readHostSnapshotCache(USER, DAY)).toBeNull()
    expect(Object.keys(sessionStorage)).toHaveLength(0)
  })

  it('odrzuca stary privacy epoch i podlega wspólnemu purge rezerwacji', () => {
    expect(writeHostSnapshotCache(USER, snapshot())).toBe(true)
    rotateReservationPrivacyEpoch()
    expect(readHostSnapshotCache(USER, DAY)).toBeNull()
    expect(Object.keys(sessionStorage)).toHaveLength(0)

    expect(writeHostSnapshotCache(USER, snapshot())).toBe(true)
    clearReservationSessions()
    expect(Object.keys(sessionStorage)).toHaveLength(0)
  })

  it('usuwa uszkodzony wpis zamiast zwracać niezweryfikowane dane', () => {
    expect(writeHostSnapshotCache(USER, snapshot())).toBe(true)
    const [key] = Object.keys(sessionStorage)
    sessionStorage.setItem(key, '{nie-json')

    expect(readHostSnapshotCache(USER, DAY)).toBeNull()
    expect(sessionStorage.getItem(key)).toBeNull()
  })

  it('nie przerywa pracy, gdy sessionStorage odrzuca zapis lub odczyt', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage blocked', 'SecurityError')
    })
    expect(() => writeHostSnapshotCache(USER, snapshot())).not.toThrow()
    expect(writeHostSnapshotCache(USER, snapshot())).toBe(false)
    setItem.mockRestore()

    expect(writeHostSnapshotCache(USER, snapshot())).toBe(true)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage blocked', 'SecurityError')
    })
    expect(() => readHostSnapshotCache(USER, DAY)).not.toThrow()
    expect(readHostSnapshotCache(USER, DAY)).toBeNull()
  })
})
