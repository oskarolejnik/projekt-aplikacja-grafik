import { useCallback, useEffect, useRef, useState } from 'react'
import { api, nowyKluczIdempotencji } from '../lib/api'
import { useBranding } from '../context/BrandingContext'
import { useToast } from '../components/ui/Toast'
import { Logo } from '../components/Logo'
import PublicReservationSearch from '../components/reservations/PublicReservationSearch'
import PublicReservationDetails from '../components/reservations/PublicReservationDetails'
import PublicReservationResult from '../components/reservations/PublicReservationResult'
import {
  LEGACY_WIDGET_CONFIG,
  availablePublicSlots,
  buildConsentPayload,
  buildPublicReservationSubmit,
  createReservationSessionId,
  normalizeManagedReservationResponse,
  normalizeWidgetConfig,
  secondsUntil,
  validatePublicGuestForm,
  warsawTodayISO,
} from '../lib/publicReservation'

const EMPTY_FORM = {
  nazwisko: '',
  telefon: '',
  email: '',
  notatka: '',
  waitlist_time: '',
  privacy_acknowledged: false,
  marketing_consent: false,
  sensitive_data: '',
  sensitive_data_consent: false,
}

const isAbortError = (error) => error?.name === 'AbortError'
const query = (value) => encodeURIComponent(String(value))

export default function RezerwacjaWidget() {
  const { nazwa_lokalu } = useBranding()
  const { toast, confirm } = useToast()
  const today = warsawTodayISO()

  const [config, setConfig] = useState(null)
  const [step, setStep] = useState('search')
  const [mode, setMode] = useState('booking')
  const [date, setDate] = useState(today)
  const [people, setPeople] = useState('2')
  const [availabilityStatus, setAvailabilityStatus] = useState('idle')
  const [slots, setSlots] = useState([])
  const [alternatives, setAlternatives] = useState([])
  const [searchError, setSearchError] = useState('')
  const [alternativesError, setAlternativesError] = useState('')
  const [slotError, setSlotError] = useState('')
  const [selectingSlot, setSelectingSlot] = useState(false)
  const [selection, setSelection] = useState(null)
  const [hold, setHold] = useState(null)
  const [holdRemaining, setHoldRemaining] = useState(null)
  const [holdExpired, setHoldExpired] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formErrors, setFormErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [resultKind, setResultKind] = useState('booking')
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const [announcement, setAnnouncement] = useState('')

  const searchHeadingRef = useRef(null)
  const detailsHeadingRef = useRef(null)
  const resultHeadingRef = useRef(null)
  const previousStepRef = useRef(step)
  const searchAbortRef = useRef(null)
  const searchSequenceRef = useRef(0)
  const sessionIdRef = useRef(createReservationSessionId())
  const holdRef = useRef(null)
  const releasedHoldTokensRef = useRef(new Set())
  const holdReleaseKeysRef = useRef(new Map())
  const holdAttemptRef = useRef(null)
  const submitAttemptRef = useRef(null)
  const cancelAttemptRef = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    api('/online/widget-config', 'GET', null, { signal: controller.signal })
      .then((value) => setConfig(normalizeWidgetConfig(value)))
      .catch((error) => {
        if (!isAbortError(error)) setConfig(LEGACY_WIDGET_CONFIG)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (previousStepRef.current === step) return undefined
    previousStepRef.current = step
    const target = step === 'search'
      ? searchHeadingRef.current
      : step === 'details'
        ? detailsHeadingRef.current
        : resultHeadingRef.current
    const timer = window.setTimeout(() => target?.focus(), 0)
    return () => window.clearTimeout(timer)
  }, [step])

  const releaseHold = useCallback((holdToken, { keepalive = false } = {}) => {
    if (!holdToken || releasedHoldTokensRef.current.has(holdToken)) return Promise.resolve()
    releasedHoldTokensRef.current.add(holdToken)
    let idempotencyKey = holdReleaseKeysRef.current.get(holdToken)
    if (!idempotencyKey) {
      idempotencyKey = nowyKluczIdempotencji('online-hold-release')
      holdReleaseKeysRef.current.set(holdToken, idempotencyKey)
    }
    return api('/online/hold', 'DELETE', null, {
      headers: {
        'X-Reservation-Session': sessionIdRef.current,
        'X-Reservation-Hold': holdToken,
        'Idempotency-Key': idempotencyKey,
      },
      keepalive,
    }).catch(() => {})
  }, [])

  useEffect(() => {
    const releaseOnPageHide = () => {
      const activeToken = holdRef.current?.hold_token
      if (activeToken) releaseHold(activeToken, { keepalive: true })
    }
    window.addEventListener('pagehide', releaseOnPageHide)
    return () => {
      window.removeEventListener('pagehide', releaseOnPageHide)
      searchAbortRef.current?.abort()
      const activeToken = holdRef.current?.hold_token
      if (activeToken) releaseHold(activeToken, { keepalive: true })
    }
  }, [releaseHold])

  useEffect(() => {
    if (!hold?.expires_at) {
      setHoldRemaining(null)
      return undefined
    }
    let expiryHandled = false
    const tick = () => {
      const remaining = secondsUntil(hold.expires_at)
      setHoldRemaining(remaining)
      if (remaining > 0 || expiryHandled) return
      expiryHandled = true
      const expiredToken = hold.hold_token
      holdRef.current = null
      setHold(null)
      setHoldExpired(true)
      setAnnouncement('Czas na dokończenie rezerwacji minął. Formularz został zachowany.')
      releaseHold(expiredToken)
    }
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [hold, releaseHold])

  const resetAvailability = useCallback(() => {
    searchAbortRef.current?.abort()
    searchSequenceRef.current += 1
    setAvailabilityStatus('idle')
    setSlots([])
    setAlternatives([])
    setSearchError('')
    setAlternativesError('')
    setSlotError('')
  }, [])

  const handleDateChange = (value) => {
    setDate(value)
    resetAvailability()
  }

  const handlePeopleChange = (value) => {
    setPeople(value)
    resetAvailability()
  }

  const loadAlternatives = useCallback(async (controller, requestDate, requestPeople) => {
    if (config.version === 1) {
      const nearest = await api(
        `/online/najblizszy-termin?od=${query(requestDate)}&osoby=${requestPeople}&dni=14`,
        'GET',
        null,
        { signal: controller.signal },
      )
      return nearest?.data && nearest?.slot
        ? [{ data: nearest.data, ...nearest.slot }]
        : []
    }
    const response = await api(
      `/online/alternatywy?data=${query(requestDate)}&osoby=${requestPeople}&limit=3`,
      'GET',
      null,
      { signal: controller.signal },
    )
    return response?.alternatywy || []
  }, [config])

  const searchAvailability = useCallback(async (event) => {
    event?.preventDefault?.()
    const requestPeople = Number(people)
    if (!date || !Number.isInteger(requestPeople) || requestPeople < 1) {
      setSearchError('Wybierz poprawną datę i liczbę osób.')
      return
    }

    searchAbortRef.current?.abort()
    const controller = new AbortController()
    searchAbortRef.current = controller
    const sequence = ++searchSequenceRef.current
    setAvailabilityStatus('loading')
    setSearchError('')
    setAlternativesError('')
    setSlotError('')
    setSlots([])
    setAlternatives([])

    try {
      const response = await api(
        `/online/dostepnosc?data=${query(date)}&osoby=${requestPeople}`,
        'GET',
        null,
        { signal: controller.signal },
      )
      if (sequence !== searchSequenceRef.current) return
      const openSlots = availablePublicSlots(response?.sloty)
      setSlots(openSlots)
      if (openSlots.length === 0) {
        try {
          const nextAlternatives = await loadAlternatives(controller, date, requestPeople)
          if (sequence !== searchSequenceRef.current) return
          setAlternatives(nextAlternatives)
        } catch (error) {
          if (isAbortError(error) || sequence !== searchSequenceRef.current) return
          setAlternativesError('Nie udało się sprawdzić innych terminów. Możesz spróbować ponownie lub dołączyć do listy oczekujących.')
        }
      }
      if (sequence !== searchSequenceRef.current) return
      setAvailabilityStatus('success')
      setAnnouncement(openSlots.length > 0
        ? `Znaleziono ${openSlots.length} dostępnych godzin.`
        : 'Brak wolnych godzin w wybranym dniu. Pokazujemy inne możliwości.')
    } catch (error) {
      if (isAbortError(error) || sequence !== searchSequenceRef.current) return
      setAvailabilityStatus('error')
      setSearchError(error?.message || 'Nie udało się sprawdzić dostępności. Sprawdź połączenie i spróbuj ponownie.')
    }
  }, [date, loadAlternatives, people])

  const selectSlot = async (slot) => {
    if (selectingSlot) return
    const nextSelection = {
      data: slot.data || date,
      godz_od: slot.godz_od,
      godz_do: slot.godz_do || null,
      liczba_osob: Number(people),
      serwis: slot.serwis || null,
    }
    setSlotError('')
    setHoldExpired(false)

    if (config.version === 1) {
      setDate(nextSelection.data)
      setSelection(nextSelection)
      setMode('booking')
      setStep('details')
      setAnnouncement(`Wybrano godzinę ${nextSelection.godz_od}.`)
      return
    }

    const body = {
      data: nextSelection.data,
      godz_od: nextSelection.godz_od,
      liczba_osob: nextSelection.liczba_osob,
    }
    const fingerprint = JSON.stringify(body)
    if (holdAttemptRef.current?.fingerprint !== fingerprint) {
      holdAttemptRef.current = {
        fingerprint,
        key: nowyKluczIdempotencji('online-hold'),
      }
    }

    setSelectingSlot(true)
    try {
      const response = await api('/online/hold', 'POST', body, {
        headers: {
          'X-Reservation-Session': sessionIdRef.current,
          'Idempotency-Key': holdAttemptRef.current.key,
        },
      })
      if (!response?.hold_token) throw new Error('Nie udało się zabezpieczyć wybranej godziny.')
      const expiresAt = response.expires_at
        || new Date(Date.now() + Math.max(1, config.hold_ttl_seconds) * 1000).toISOString()
      const nextHold = { hold_token: response.hold_token, expires_at: expiresAt }
      holdRef.current = nextHold
      setHold(nextHold)
      setHoldRemaining(secondsUntil(expiresAt))
      setDate(response.rezerwacja?.data || nextSelection.data)
      setSelection({ ...nextSelection, ...(response.rezerwacja || {}) })
      setMode('booking')
      setStep('details')
      setAnnouncement(`Godzina ${nextSelection.godz_od} została tymczasowo zabezpieczona.`)
    } catch (error) {
      if (error?.status === 409 || error?.code === 'IDEMPOTENCY_KEY_REUSED') holdAttemptRef.current = null
      setSlotError(error?.message || 'Nie udało się zabezpieczyć tej godziny. Odśwież dostępność i spróbuj ponownie.')
    } finally {
      setSelectingSlot(false)
    }
  }

  const joinWaitlist = () => {
    setSelection({ data: date, godz_od: null, liczba_osob: Number(people) })
    setMode('waitlist')
    setHoldExpired(false)
    setSubmitError('')
    setStep('details')
    setAnnouncement('Otworzono formularz listy oczekujących.')
  }

  const backToSearch = () => {
    const activeToken = holdRef.current?.hold_token
    holdRef.current = null
    setHold(null)
    if (activeToken) releaseHold(activeToken)
    setHoldExpired(false)
    setSubmitError('')
    setFormErrors({})
    setStep('search')
    setAnnouncement('Wrócono do wyboru terminu. Wpisane dane zostały zachowane.')
  }

  const changeForm = (field, value) => {
    setForm((current) => {
      const next = { ...current, [field]: value }
      if (field === 'sensitive_data' && !String(value).trim()) next.sensitive_data_consent = false
      return next
    })
    setFormErrors((current) => {
      const clearsContact = (field === 'telefon' || field === 'email') && current.contact
      if (!current[field] && !clearsContact && !(field === 'sensitive_data' && current.sensitive_data_consent)) return current
      const next = { ...current }
      delete next[field]
      if (clearsContact) delete next.contact
      if (field === 'sensitive_data') delete next.sensitive_data_consent
      return next
    })
    setSubmitError('')
  }

  const submitReservation = async (event) => {
    event.preventDefault()
    if (busy || !selection) return
    const errors = validatePublicGuestForm(form, { requireContact: config.version === 2 })
    setFormErrors(errors)
    if (Object.keys(errors).length > 0) {
      setSubmitError('Sprawdź oznaczone pola i spróbuj ponownie.')
      setAnnouncement('Formularz zawiera błędy.')
      return
    }

    const consent = buildConsentPayload(form, config)
    const body = {
      data: selection.data,
      godz_od: mode === 'waitlist' ? (form.waitlist_time || null) : selection.godz_od,
      liczba_osob: Number(selection.liczba_osob),
      nazwisko: form.nazwisko.trim(),
      telefon: form.telefon.trim() || null,
      email: form.email.trim() || null,
      notatka: form.notatka.trim() || null,
      ...consent,
    }
    const endpoint = mode === 'waitlist' ? '/online/lista-oczekujacych' : '/online/rezerwacja'
    const request = buildPublicReservationSubmit({
      endpoint,
      body,
      sessionId: sessionIdRef.current,
      holdToken: mode === 'booking' ? holdRef.current?.hold_token : null,
    })
    const fingerprint = request.fingerprint
    if (submitAttemptRef.current?.fingerprint !== fingerprint) {
      submitAttemptRef.current = {
        fingerprint,
        key: nowyKluczIdempotencji(mode === 'waitlist' ? 'online-waitlist' : 'online-reservation'),
      }
    }

    setBusy(true)
    setSubmitError('')
    try {
      const response = await api(endpoint, 'POST', request.body, {
        headers: {
          ...request.headers,
          'Idempotency-Key': submitAttemptRef.current.key,
        },
      })
      submitAttemptRef.current = null
      if (mode === 'booking') {
        const consumedToken = holdRef.current?.hold_token
        if (consumedToken) releasedHoldTokensRef.current.add(consumedToken)
        holdRef.current = null
        setHold(null)
        setResult(normalizeManagedReservationResponse(response))
      } else {
        const { token: _unusedToken, ...safeResponse } = response || {}
        setResult({ ...safeResponse, wpis: response?.wpis || response?.rezerwacja || safeResponse })
      }
      setResultKind(mode)
      setStep('result')
      setAnnouncement(mode === 'waitlist' ? 'Dodano do listy oczekujących.' : 'Rezerwacja została przyjęta.')
    } catch (error) {
      if (error?.code === 'IDEMPOTENCY_KEY_REUSED' || error?.status === 409) submitAttemptRef.current = null
      const holdRejected = mode === 'booking' && config.version === 2
        && (error?.status === 409 || /HOLD|hold|wygas/i.test(`${error?.code || ''} ${error?.message || ''}`))
      if (holdRejected) {
        const rejectedToken = holdRef.current?.hold_token
        holdRef.current = null
        setHold(null)
        setHoldExpired(true)
        if (rejectedToken) releaseHold(rejectedToken)
      }
      setSubmitError(error?.message || 'Nie udało się zapisać. Twoje dane pozostały w formularzu — spróbuj ponownie.')
    } finally {
      setBusy(false)
    }
  }

  const cancelReservation = async () => {
    const token = result?.management_token
    if (!token || cancelling) return
    const accepted = await confirm(
      'Termin zostanie zwolniony dla innych gości. Tej czynności nie można cofnąć.',
      {
        title: 'Odwołać rezerwację?',
        confirmText: 'Odwołaj rezerwację',
        cancelText: 'Zachowaj termin',
        danger: true,
      },
    )
    if (!accepted) return

    if (cancelAttemptRef.current?.token !== token) {
      cancelAttemptRef.current = {
        token,
        key: nowyKluczIdempotencji('online-reservation-cancel'),
      }
    }
    setCancelling(true)
    setCancelError('')
    try {
      const response = await api('/online/zarzadzanie/odwolaj', 'POST', null, {
        headers: {
          'X-Reservation-Session': sessionIdRef.current,
          'X-Reservation-Token': token,
          'Idempotency-Key': cancelAttemptRef.current.key,
        },
      })
      setResult(normalizeManagedReservationResponse(response, token))
      cancelAttemptRef.current = null
      setAnnouncement('Rezerwacja została odwołana.')
      toast('Rezerwacja została odwołana.', 'info')
    } catch (error) {
      if (error?.code === 'IDEMPOTENCY_KEY_REUSED') cancelAttemptRef.current = null
      setCancelError(error?.message || 'Nie udało się odwołać rezerwacji. Spróbuj ponownie.')
    } finally {
      setCancelling(false)
    }
  }

  const newReservation = () => {
    setStep('search')
    setMode('booking')
    setResult(null)
    setSelection(null)
    setForm(EMPTY_FORM)
    setFormErrors({})
    setSubmitError('')
    setCancelError('')
    setDate(warsawTodayISO())
    setPeople('2')
    resetAvailability()
    setAnnouncement('Możesz wyszukać nowy termin.')
  }

  return (
    <main className="relative min-h-dvh bg-bg px-safe pb-safe pt-safe text-ink">
      <div aria-hidden="true" className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto w-full max-w-lg py-8 sm:py-10">
        <header className="mb-6 flex items-center gap-3">
          <Logo className="h-10" />
          <div className="min-w-0">
            <h1 className="truncate font-display text-xl font-semibold tracking-tight text-ink">{nazwa_lokalu}</h1>
            <p className="text-sm text-muted">Rezerwacja stolika online</p>
          </div>
        </header>

        <div className="card p-5 sm:p-8">
          {!config ? (
            <div className="py-10 text-center" role="status">
              <p className="text-sm text-muted">Przygotowuję rezerwację…</p>
            </div>
          ) : !config.ready ? (
            <section className="py-6" aria-labelledby="public-reservation-unavailable-title" role="alert">
              <h2 id="public-reservation-unavailable-title" className="font-display text-xl font-semibold tracking-tight text-ink">
                Rezerwacje online są chwilowo niedostępne
              </h2>
              <p className="mt-2 text-base leading-relaxed text-muted">
                Lokal kończy konfigurację bezpiecznego formularza. Skontaktuj się bezpośrednio z obsługą, aby zarezerwować stolik.
              </p>
            </section>
          ) : step === 'search' ? (
            <PublicReservationSearch
              headingRef={searchHeadingRef}
              date={date}
              people={people}
              minDate={today}
              status={availabilityStatus}
              slots={slots}
              alternatives={alternatives}
              error={searchError}
              alternativesError={alternativesError}
              slotError={slotError}
              selectingSlot={selectingSlot}
              onDateChange={handleDateChange}
              onPeopleChange={handlePeopleChange}
              onSearch={searchAvailability}
              onSelectSlot={selectSlot}
              onJoinWaitlist={joinWaitlist}
            />
          ) : step === 'details' && selection ? (
            <PublicReservationDetails
              headingRef={detailsHeadingRef}
              mode={mode}
              selection={selection}
              form={form}
              config={config}
              errors={formErrors}
              submitError={submitError}
              busy={busy}
              holdRemaining={holdRemaining}
              holdExpired={holdExpired}
              onChange={changeForm}
              onBack={backToSearch}
              onChooseAnother={backToSearch}
              onSubmit={submitReservation}
            />
          ) : step === 'result' && result ? (
            <PublicReservationResult
              headingRef={resultHeadingRef}
              result={result}
              kind={resultKind}
              cancelling={cancelling}
              cancelError={cancelError}
              onCancel={cancelReservation}
              onNewReservation={newReservation}
            />
          ) : null}
        </div>

        <footer className="mt-5 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-sm text-muted">
          <span>{nazwa_lokalu}</span>
          <span aria-hidden="true">·</span>
          <a href="/?polityka" className="inline-flex min-h-11 items-center font-medium text-ink underline decoration-line underline-offset-4 hover:decoration-mint">
            Prywatność
          </a>
        </footer>
      </div>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
    </main>
  )
}
