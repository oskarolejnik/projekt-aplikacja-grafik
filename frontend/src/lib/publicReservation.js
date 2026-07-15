const WARSAW_TIME_ZONE = 'Europe/Warsaw'

export const LEGACY_WIDGET_CONFIG = Object.freeze({
  version: 1,
  ready: true,
  hold_ttl_seconds: 0,
  privacy: {
    notice_version: 'legacy-v1',
    notice_label: 'Zapoznałem/am się z informacją o przetwarzaniu danych.',
    notice_text: null,
  },
  marketing: {
    version: 'legacy-v1',
    label: 'Chcę otrzymywać okazjonalne informacje i oferty.',
  },
  sensitive: {
    version: 'legacy-v1',
    label: 'Zgadzam się na wykorzystanie podanych informacji wyłącznie do obsługi tej wizyty.',
  },
})

export function normalizeWidgetConfig(value) {
  const version = Number(value?.version) === 2 ? 2 : 1
  return {
    version,
    ready: value?.ready !== false,
    hold_ttl_seconds: Math.max(0, Number(value?.hold_ttl_seconds) || 0),
    privacy: {
      notice_version: value?.privacy?.notice_version || LEGACY_WIDGET_CONFIG.privacy.notice_version,
      notice_label: value?.privacy?.notice_label || LEGACY_WIDGET_CONFIG.privacy.notice_label,
      notice_text: value?.privacy?.notice_text || null,
    },
    marketing: {
      version: value?.marketing?.version || LEGACY_WIDGET_CONFIG.marketing.version,
      label: value?.marketing?.label || LEGACY_WIDGET_CONFIG.marketing.label,
    },
    sensitive: {
      version: value?.sensitive?.version || LEGACY_WIDGET_CONFIG.sensitive.version,
      label: value?.sensitive?.label || LEGACY_WIDGET_CONFIG.sensitive.label,
    },
  }
}

export function warsawTodayISO(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: WARSAW_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return `${values.year}-${values.month}-${values.day}`
}

export function formatReservationDate(date) {
  if (!date) return ''
  return new Intl.DateTimeFormat('pl-PL', {
    timeZone: WARSAW_TIME_ZONE,
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(new Date(`${date}T12:00:00Z`))
}

export function availablePublicSlots(slots = []) {
  return slots.filter((slot) => slot?.dostepny === true || Number(slot?.wolne) > 0)
}

export function secondsUntil(expiresAt, nowMs = Date.now()) {
  const rawValue = String(expiresAt || '')
  const normalizedValue = rawValue && !/(?:z|[+-]\d{2}:?\d{2})$/i.test(rawValue)
    ? `${rawValue}Z`
    : rawValue
  const expiresMs = Date.parse(normalizedValue)
  if (!Number.isFinite(expiresMs)) return 0
  return Math.max(0, Math.ceil((expiresMs - nowMs) / 1000))
}

export function formatCountdown(totalSeconds) {
  const seconds = Math.max(0, Math.floor(Number(totalSeconds) || 0))
  const minutesPart = Math.floor(seconds / 60).toString().padStart(2, '0')
  const secondsPart = (seconds % 60).toString().padStart(2, '0')
  return `${minutesPart}:${secondsPart}`
}

export function createReservationSessionId() {
  const random = globalThis.crypto?.randomUUID?.()
    || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `reservation-session-${random}`.slice(0, 128)
}

export function buildConsentPayload(form, config) {
  const sensitiveData = form.sensitive_data.trim()
  const marketingConsent = Boolean(form.marketing_consent)
  return {
    privacy_notice_version: config.privacy.notice_version,
    privacy_notice_acknowledged: Boolean(form.privacy_acknowledged),
    marketing_consent: marketingConsent,
    marketing_consent_version: marketingConsent ? config.marketing.version : null,
    sensitive_data: sensitiveData || null,
    sensitive_data_consent: sensitiveData
      ? Boolean(form.sensitive_data_consent)
      : false,
    sensitive_data_consent_version: sensitiveData ? config.sensitive.version : null,
  }
}

export function buildPublicReservationSubmit({ endpoint, body, sessionId, holdToken = null }) {
  const safeBody = { ...(body || {}) }
  delete safeBody.hold_token

  return {
    body: safeBody,
    fingerprint: JSON.stringify({ endpoint, body: safeBody }),
    headers: {
      'X-Reservation-Session': sessionId,
      ...(holdToken ? { 'X-Reservation-Hold': holdToken } : {}),
    },
  }
}

export function validatePublicGuestForm(form, { requireContact = false } = {}) {
  const errors = {}
  if (!form.nazwisko.trim()) errors.nazwisko = 'Podaj imię i nazwisko.'
  if (requireContact && !form.telefon.trim() && !form.email.trim()) {
    errors.contact = 'Podaj telefon lub e-mail, aby lokal mógł skontaktować się w sprawie rezerwacji.'
  }
  if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
    errors.email = 'Wpisz poprawny adres e-mail.'
  }
  if (!form.privacy_acknowledged) {
    errors.privacy_acknowledged = 'Potwierdź zapoznanie się z informacją o przetwarzaniu danych.'
  }
  if (form.sensitive_data.trim() && !form.sensitive_data_consent) {
    errors.sensitive_data_consent = 'Potwierdź zgodę na przetwarzanie podanych danych wrażliwych.'
  }
  return errors
}

export function normalizeManagedReservationResponse(response, previousToken = null) {
  return {
    ...response,
    management_token: response?.management_token || response?.token || previousToken,
    rezerwacja: response?.rezerwacja || response,
  }
}
