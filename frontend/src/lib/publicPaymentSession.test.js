// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearPublicPaymentSession,
  readPublicPaymentSession,
  savePublicPaymentSession,
} from './publicPaymentSession'

describe('publicPaymentSession', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('przechowuje wyłącznie bezpieczny snapshot bez capability, linku Checkout i PII', () => {
    savePublicPaymentSession({
      managementToken: 'capability-secret',
      reservation: {
        id: 12,
        data: '2026-07-20',
        godz_od: '18:00',
        liczba_osob: 4,
        status: 'potwierdzona',
        nazwisko: 'Kowalska',
        telefon: '500600700',
        email: 'gosc@example.com',
      },
      payment: {
        id: 3,
        status: 'oczekuje',
        amount_minor: 8000,
        currency: 'pln',
        checkout_url: 'https://checkout.stripe.test/cs_secret',
        provider_payment_intent_id: 'pi_secret',
      },
    })

    const raw = JSON.stringify(sessionStorage)
    expect(raw).not.toContain('capability-secret')
    expect(raw).not.toContain('cs_secret')
    expect(raw).not.toContain('pi_secret')
    expect(raw).not.toContain('Kowalska')
    expect(raw).not.toContain('500600700')
    expect(raw).not.toContain('gosc@example.com')
    expect(readPublicPaymentSession()?.reservation).toEqual({
      id: 12,
      data: '2026-07-20',
      godz_od: '18:00',
      liczba_osob: 4,
      status: 'potwierdzona',
    })
    expect(readPublicPaymentSession()?.payment).toEqual({
      id: 3,
      status: 'oczekuje',
      rodzaj: null,
      kwota_minor: 8000,
      waluta: 'pln',
      wygasa_at: null,
      zwrocono_minor: 0,
      refund_status: 'brak',
      po_niepowodzeniu: null,
      mozna_ponowic: false,
      tryb_demo: false,
    })
  })

  it('usuwa historyczny wpis v1 zawierający plaintext token', () => {
    sessionStorage.setItem('lokalo:public-payment:v1', JSON.stringify({
      managementToken: 'old-capability-secret',
    }))

    expect(readPublicPaymentSession()).toBeNull()
    expect(JSON.stringify(sessionStorage)).not.toContain('old-capability-secret')
  })

  it('czyści sesję jawnie', () => {
    savePublicPaymentSession({
      managementToken: 'token',
      reservation: { id: 1 },
      payment: { id: 1, status: 'oczekuje' },
    })
    clearPublicPaymentSession()
    expect(readPublicPaymentSession()).toBeNull()
  })
})
