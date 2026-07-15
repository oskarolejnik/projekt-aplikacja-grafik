import { describe, expect, it } from 'vitest'
import {
  LEGACY_WIDGET_CONFIG,
  availablePublicSlots,
  buildConsentPayload,
  buildPublicReservationSubmit,
  formatCountdown,
  normalizeManagedReservationResponse,
  normalizeWidgetConfig,
  secondsUntil,
  validatePublicGuestForm,
  warsawTodayISO,
} from './publicReservation'

describe('publicReservation helpers', () => {
  it('wyznacza dzień w strefie Europe/Warsaw zamiast według UTC', () => {
    expect(warsawTodayISO(new Date('2026-07-14T22:30:00.000Z'))).toBe('2026-07-15')
  })

  it('normalizuje konfigurację v2 i bezpieczny fallback v1', () => {
    expect(normalizeWidgetConfig({ version: 2, hold_ttl_seconds: 600, privacy: { notice_version: '2026-07' } })).toMatchObject({
      version: 2,
      ready: true,
      hold_ttl_seconds: 600,
      privacy: { notice_version: '2026-07' },
    })
    expect(normalizeWidgetConfig({ version: 2, ready: false })).toMatchObject({ version: 2, ready: false })
    expect(normalizeWidgetConfig(null)).toEqual(LEGACY_WIDGET_CONFIG)
  })

  it('pokazuje wyłącznie publicznie dostępne sloty bez interpretowania zapasu', () => {
    expect(availablePublicSlots([
      { godz_od: '17:00', dostepny: true, wolne: 0 },
      { godz_od: '18:00', dostepny: false, wolne: 0 },
      { godz_od: '19:00', wolne: 1 },
    ])).toEqual([
      { godz_od: '17:00', dostepny: true, wolne: 0 },
      { godz_od: '19:00', wolne: 1 },
    ])
  })

  it('liczy i formatuje czas holda bez wartości ujemnych', () => {
    expect(secondsUntil('2026-07-15T18:10:00.000Z', Date.parse('2026-07-15T18:00:00.000Z'))).toBe(600)
    expect(secondsUntil('2026-07-15T18:10:00', Date.parse('2026-07-15T18:00:00.000Z'))).toBe(600)
    expect(secondsUntil('2026-07-15T17:59:00.000Z', Date.parse('2026-07-15T18:00:00.000Z'))).toBe(0)
    expect(formatCountdown(600)).toBe('10:00')
    expect(formatCountdown(9)).toBe('00:09')
  })

  it('oddziela obowiązkową informację, niewybraną zgodę marketingową i dane wrażliwe', () => {
    const form = {
      privacy_acknowledged: true,
      marketing_consent: false,
      sensitive_data: '  alergia na orzechy  ',
      sensitive_data_consent: true,
    }
    expect(buildConsentPayload(form, normalizeWidgetConfig({
      version: 2,
      privacy: { notice_version: 'privacy-2' },
    }))).toEqual({
      privacy_notice_version: 'privacy-2',
      privacy_notice_acknowledged: true,
      marketing_consent: false,
      marketing_consent_version: null,
      sensitive_data: 'alergia na orzechy',
      sensitive_data_consent: true,
      sensitive_data_consent_version: 'legacy-v1',
    })
  })

  it('wymaga zgody na dane wrażliwe tylko wtedy, gdy gość je podał', () => {
    const base = {
      nazwisko: 'Jan Kowalski',
      telefon: '',
      email: '',
      privacy_acknowledged: true,
      sensitive_data: '',
      sensitive_data_consent: false,
    }
    expect(validatePublicGuestForm(base)).toEqual({})
    expect(validatePublicGuestForm(base, { requireContact: true })).toEqual({
      contact: 'Podaj telefon lub e-mail, aby lokal mógł skontaktować się w sprawie rezerwacji.',
    })
    expect(validatePublicGuestForm({ ...base, sensitive_data: 'celiakia' })).toEqual({
      sensitive_data_consent: 'Potwierdź zgodę na przetwarzanie podanych danych wrażliwych.',
    })
  })

  it('przenosi sekret holda wyłącznie do nagłówka, poza body i fingerprint', () => {
    const request = buildPublicReservationSubmit({
      endpoint: '/online/rezerwacja',
      body: { data: '2035-07-16', hold_token: 'raw-hold-secret' },
      sessionId: 'reservation-session-test',
      holdToken: 'raw-hold-secret',
    })

    expect(request.body).toEqual({ data: '2035-07-16' })
    expect(request.fingerprint).not.toContain('raw-hold-secret')
    expect(request.headers).toEqual({
      'X-Reservation-Session': 'reservation-session-test',
      'X-Reservation-Hold': 'raw-hold-secret',
    })
  })

  it('przyjmuje obrócony token zarządzania bez ujawniania go w danych rezerwacji', () => {
    expect(normalizeManagedReservationResponse({
      management_token: 'rotated',
      rezerwacja: { status: 'odwolana' },
    }, 'old')).toMatchObject({
      management_token: 'rotated',
      rezerwacja: { status: 'odwolana' },
    })
  })
})
