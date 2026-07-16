const KEY = 'lokalo:public-payment:v2'
const LEGACY_KEYS = ['lokalo:public-payment:v1']
const TTL_MS = 30 * 60 * 1000

const safeReservation = (reservation = {}) => ({
  id: reservation.id ?? null,
  data: reservation.data ?? null,
  godz_od: reservation.godz_od ?? null,
  liczba_osob: reservation.liczba_osob ?? null,
  status: reservation.status ?? null,
})

const safePayment = (payment = {}) => ({
  id: payment.id ?? null,
  status: payment.status ?? null,
  rodzaj: payment.rodzaj ?? payment.kind ?? null,
  kwota_minor: payment.kwota_minor ?? payment.amount_minor ?? null,
  waluta: payment.waluta ?? payment.currency ?? null,
  wygasa_at: payment.wygasa_at ?? null,
  zwrocono_minor: payment.zwrocono_minor ?? 0,
  refund_status: payment.refund_status ?? 'brak',
  po_niepowodzeniu: payment.po_niepowodzeniu ?? payment.failure_action ?? null,
  mozna_ponowic: payment.mozna_ponowic ?? payment.can_retry ?? false,
  tryb_demo: payment.tryb_demo === true,
})

const removeLegacyEntries = () => {
  for (const key of LEGACY_KEYS) sessionStorage.removeItem(key)
}

export function savePublicPaymentSession({ reservation, payment }) {
  if (!payment || typeof sessionStorage === 'undefined') return
  try {
    // Wersja v1 zawierała capability zarządzania. Usuwamy ją przy pierwszym
    // kontakcie z nowym klientem, zamiast czekać na naturalne zamknięcie karty.
    removeLegacyEntries()
    sessionStorage.setItem(KEY, JSON.stringify({
      expiresAt: Date.now() + TTL_MS,
      reservation: safeReservation(reservation),
      // Link Checkout także jest credentialem. Snapshot służy wyłącznie do
      // stabilnego pierwszego renderu; kanoniczny link przychodzi ponownie z API.
      payment: safePayment(payment),
    }))
  } catch {
    // Prywatny tryb lub brak miejsca nie może zablokować płatności w bieżącej karcie.
  }
}

export function readPublicPaymentSession() {
  if (typeof sessionStorage === 'undefined') return null
  try {
    removeLegacyEntries()
    const value = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    if (!value || value.expiresAt <= Date.now() || !value.payment) {
      sessionStorage.removeItem(KEY)
      return null
    }
    return value
  } catch {
    sessionStorage.removeItem(KEY)
    return null
  }
}

export function clearPublicPaymentSession() {
  if (typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.removeItem(KEY)
    removeLegacyEntries()
  } catch {
    // Best effort.
  }
}
