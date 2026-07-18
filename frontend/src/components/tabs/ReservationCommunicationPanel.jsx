import { useCallback, useEffect, useRef, useState } from 'react'
import { api, nowyKluczIdempotencji } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { InlineFeedback } from '../ui/InlineFeedback'
import { Spinner } from '../ui/Spinner'
import ReservationCommunicationStatus from './ReservationCommunicationStatus'

const PENDING_STATES = new Set(['queued', 'processing', 'retry'])
const HISTORY_REFRESH_CONFLICTS = new Set([
  'COMMUNICATION_ALREADY_PENDING',
  'COMMUNICATION_RESEND_CONFIRMATION_REQUIRED',
  'COMMUNICATION_RETRY_REQUIRED',
  'COMMUNICATION_RECONCILIATION_REQUIRED',
])
const CHANNEL_LABELS = { email: 'E-mail', sms: 'SMS' }
const WAITLIST_STALE_DELIVERED_CODE = 'WAITLIST_STALE_TABLE_READY_DELIVERED'

const isStaleDelivered = (message) => Boolean(
  message?.state === 'uncertain'
  && message?.sent_at
  && message?.last_error_code === WAITLIST_STALE_DELIVERED_CODE
)

const OWNER_META = {
  reservation: {
    event: 'confirmation',
    historyPath: (id) => `/rezerwacje-stolik/${id}/komunikacja`,
    queuePath: (id) => `/rezerwacje-stolik/${id}/wyslij-potwierdzenie`,
    queueLabel: 'Wyślij potwierdzenie',
    resendLabel: 'Wyślij potwierdzenie ponownie',
    queueSuccess: 'Dodano potwierdzenie do kolejki.',
    pendingLabel: 'Potwierdzenie jest już w kolejce.',
    emptyLabel: 'Nie ma jeszcze wiadomości dla tej rezerwacji.',
    disabledChangesLabel: 'Zapisz albo cofnij zmiany w rezerwacji przed kolejną wiadomością.',
    help: 'Potwierdzenia i przypomnienia operacyjne. Niezależne od zgód marketingowych.',
    keyScope: 'reservation-confirmation',
    confirmTitle: 'Wysłać potwierdzenie ponownie?',
    confirmText: 'Dodaj ponownie',
    confirmMessage: 'Potwierdzenie było już wysyłane. Dodać nową wiadomość do kolejki? Gość może otrzymać kolejny egzemplarz.',
  },
  waitlist: {
    event: 'table_ready',
    historyPath: (id) => `/lista-oczekujacych/${id}/komunikacja`,
    queuePath: (id) => `/lista-oczekujacych/${id}/powiadom`,
    queueLabel: 'Powiadom: stolik gotowy',
    resendLabel: 'Powiadom ponownie: stolik gotowy',
    queueSuccess: 'Dodano powiadomienie „stolik gotowy” do kolejki.',
    pendingLabel: 'Powiadomienie „stolik gotowy” jest już w kolejce.',
    emptyLabel: 'Nie ma jeszcze wiadomości dla tego wpisu.',
    disabledChangesLabel: 'Ten wpis nie oczekuje już na stolik.',
    help: 'Powiadomienie o gotowym stoliku i jego historia dostarczenia.',
    keyScope: 'waitlist-table-ready',
    confirmTitle: 'Powiadomić ponownie?',
    confirmText: 'Dodaj ponownie',
    confirmMessage: 'Powiadomienie o gotowym stoliku było już wysyłane. Dodać kolejne do kolejki? Gość może otrzymać duplikat.',
  },
}

const formatTimestamp = (value) => {
  if (!value) return null
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('pl-PL', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Warsaw',
  }).format(date)
}

const actionKey = (type, messageId) => `${type}:${messageId}`

export default function ReservationCommunicationPanel({
  ownerType = 'reservation',
  ownerId,
  // Tymczasowy alias zachowuje kompatybilność wywołań podczas migracji panelu.
  reservationId,
  initialSummary = null,
  canQueue = true,
  communicationPreference = 'auto',
  actionsDisabled = false,
  manualAlreadyHandled = false,
  showQueueAction = true,
  confirmAction,
  onSummaryChange,
}) {
  const resolvedOwnerId = ownerId ?? reservationId
  const meta = OWNER_META[ownerType] || OWNER_META.reservation
  const ownerKey = `${ownerType}:${resolvedOwnerId ?? ''}`
  const panelId = `communication-${ownerType}-${resolvedOwnerId ?? 'unknown'}`
  const ownerKeyRef = useRef(ownerKey)
  ownerKeyRef.current = ownerKey

  const [history, setHistory] = useState({ ownerKey, summary: initialSummary, messages: [] })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [refreshError, setRefreshError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [action, setAction] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [notes, setNotes] = useState({})
  const [queueCommitted, setQueueCommitted] = useState(false)
  const readControllerRef = useRef(null)
  const actionControllerRef = useRef(null)
  const actionLockRef = useRef(null)
  const manualQueueAttemptRef = useRef(null)
  const mountedRef = useRef(true)

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!resolvedOwnerId) return false
    const requestOwnerKey = ownerKey
    readControllerRef.current?.abort()
    const controller = new AbortController()
    readControllerRef.current = controller
    if (silent) {
      setRefreshing(true)
      setRefreshError(null)
    } else {
      setLoading(true)
      setLoadError(null)
      setRefreshError(null)
    }
    try {
      const result = await api(meta.historyPath(resolvedOwnerId), 'GET', null, { signal: controller.signal })
      if (controller.signal.aborted || !mountedRef.current || ownerKeyRef.current !== requestOwnerKey) return false
      const next = {
        ownerKey: requestOwnerKey,
        summary: result?.summary || null,
        messages: Array.isArray(result?.messages) ? result.messages : [],
        manualConfirmationStatePresent: Object.prototype.hasOwnProperty.call(result || {}, 'manual_confirmation_state'),
        manualConfirmationState: result?.manual_confirmation_state ?? null,
        manualConfirmationResendRequiredPresent: Object.prototype.hasOwnProperty.call(result || {}, 'manual_confirmation_resend_required'),
        manualConfirmationResendRequired: Boolean(result?.manual_confirmation_resend_required),
      }
      setHistory(next)
      if (
        next.messages.some((message) => message.event === meta.event)
        || next.summary?.event === meta.event
        || (next.manualConfirmationStatePresent && next.manualConfirmationState !== null)
      ) {
        setQueueCommitted(false)
      }
      onSummaryChange?.(next.summary, { type: ownerType, id: resolvedOwnerId })
      return true
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError' || !mountedRef.current || ownerKeyRef.current !== requestOwnerKey) return false
      const message = error.message || 'Nie udało się pobrać historii komunikacji.'
      if (silent) setRefreshError(message)
      else setLoadError(message)
      return false
    } finally {
      if (controller.signal.aborted || !mountedRef.current || ownerKeyRef.current !== requestOwnerKey) return
      if (readControllerRef.current === controller) readControllerRef.current = null
      setLoading(false)
      setRefreshing(false)
    }
  }, [meta, onSummaryChange, ownerKey, ownerType, resolvedOwnerId])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      readControllerRef.current?.abort()
      actionControllerRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    readControllerRef.current?.abort()
    actionControllerRef.current?.abort()
    actionControllerRef.current = null
    actionLockRef.current = null
    manualQueueAttemptRef.current = null
    setHistory({ ownerKey, summary: initialSummary, messages: [] })
    setLoading(true)
    setLoadError(null)
    setRefreshError(null)
    setRefreshing(false)
    setAction(null)
    setFeedback(null)
    setNotes({})
    setQueueCommitted(false)
    void load()
    return () => {
      readControllerRef.current?.abort()
      actionControllerRef.current?.abort()
    }
  }, [ownerKey, load]) // Początkowy snapshot jest tylko pomostem do świeżej historii z API.

  const visibleHistory = history.ownerKey === ownerKey
    ? history
    : { ownerKey, summary: initialSummary, messages: [] }
  const visibleLoading = history.ownerKey !== ownerKey || loading

  useEffect(() => {
    const shouldPoll = queueCommitted
      || PENDING_STATES.has(visibleHistory.summary?.state)
      || PENDING_STATES.has(visibleHistory.manualConfirmationState)
      || visibleHistory.messages.some((message) => PENDING_STATES.has(message.state))
    if (visibleLoading || loadError || refreshing || action || !shouldPoll) return undefined
    const timer = window.setTimeout(() => { void load({ silent: true }) }, 3000)
    return () => window.clearTimeout(timer)
  }, [
    action,
    load,
    loadError,
    queueCommitted,
    refreshing,
    visibleHistory.manualConfirmationState,
    visibleHistory.messages,
    visibleHistory.summary?.state,
    visibleLoading,
  ])

  const runAction = async (key, request, successMessage, { clearManualAttempt = false, onSuccess } = {}) => {
    if (actionLockRef.current || actionsDisabled) return false
    const requestOwnerKey = ownerKey
    const controller = new AbortController()
    actionControllerRef.current?.abort()
    actionControllerRef.current = controller
    actionLockRef.current = { ownerKey: requestOwnerKey, key }
    setAction(key)
    setFeedback(null)
    try {
      const result = await request(controller.signal)
      if (controller.signal.aborted || !mountedRef.current || ownerKeyRef.current !== requestOwnerKey) return false
      if (clearManualAttempt) manualQueueAttemptRef.current = null
      onSuccess?.(result)
      setFeedback({ type: 'success', message: successMessage })
      await load({ silent: true })
      return true
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError' || !mountedRef.current || ownerKeyRef.current !== requestOwnerKey) return false
      setFeedback({ type: 'error', message: error.message || 'Nie udało się zapisać operacji.' })
      if (error?.status === 409 && HISTORY_REFRESH_CONFLICTS.has(error?.code)) {
        await load({ silent: true })
      }
      return false
    } finally {
      if (ownerKeyRef.current === requestOwnerKey) {
        setAction(null)
        if (actionLockRef.current?.ownerKey === requestOwnerKey) actionLockRef.current = null
      }
      if (actionControllerRef.current === controller) actionControllerRef.current = null
    }
  }

  const latestManualMessage = visibleHistory.messages.find((message) => message.event === meta.event)
  const summaryMatchesManualEvent = visibleHistory.summary?.event === meta.event
  const canonicalManualStateAvailable = ownerType === 'reservation'
    && visibleHistory.manualConfirmationStatePresent
  const fallbackManualState = summaryMatchesManualEvent
    ? visibleHistory.summary?.state
    : latestManualMessage?.state
  const manualState = canonicalManualStateAvailable
    ? visibleHistory.manualConfirmationState
    : fallbackManualState
  const hasManualMessage = canonicalManualStateAvailable
    ? manualState !== null
    : Boolean(latestManualMessage || summaryMatchesManualEvent)
  const manualResendRequired = ownerType === 'reservation' && (
    visibleHistory.manualConfirmationResendRequiredPresent
      ? visibleHistory.manualConfirmationResendRequired
      : manualState === 'sent'
  )
  const waitlistAlreadyHandled = ownerType === 'waitlist' && Boolean(
    hasManualMessage
    || manualAlreadyHandled
    || visibleHistory.summary?.legacy_delivery,
  )
  let manualBlockReason = null
  if (queueCommitted || PENDING_STATES.has(manualState)) {
    manualBlockReason = meta.pendingLabel
  } else if (manualState === 'uncertain') {
    manualBlockReason = 'Najpierw uzgodnij niepewny wynik, aby uniknąć duplikatu.'
  } else if (manualState === 'failed') {
    manualBlockReason = 'Poprzednia wiadomość nie została dostarczona. Użyj akcji „Ponów” przy tej wiadomości.'
  } else if (waitlistAlreadyHandled) {
    manualBlockReason = 'Gość został już powiadomiony o gotowym stoliku. Historia pozostaje dostępna poniżej.'
  }

  const queueMessage = async () => {
    if (!showQueueAction || actionLockRef.current || actionsDisabled || visibleLoading || loadError || manualBlockReason) return
    const requestOwnerKey = ownerKey
    let confirmResend = false
    if (ownerType === 'reservation' && hasManualMessage) {
      actionLockRef.current = { ownerKey: requestOwnerKey, key: 'queue-confirm' }
      setAction('queue-confirm')
      let approved = false
      try {
        approved = Boolean(await confirmAction?.(meta.confirmMessage, {
          title: meta.confirmTitle,
          confirmText: meta.confirmText,
          cancelText: 'Nie wysyłaj',
        }))
      } catch {
        if (mountedRef.current && ownerKeyRef.current === requestOwnerKey) {
          setFeedback({ type: 'error', message: 'Nie udało się otworzyć potwierdzenia ponownej wysyłki.' })
        }
      }
      if (!mountedRef.current || ownerKeyRef.current !== requestOwnerKey) return
      actionLockRef.current = null
      setAction(null)
      if (!approved) return
      confirmResend = manualResendRequired
    }

    let attempt = manualQueueAttemptRef.current
    if (!attempt || attempt.ownerKey !== requestOwnerKey || attempt.event !== meta.event) {
      attempt = {
        ownerKey: requestOwnerKey,
        event: meta.event,
        key: nowyKluczIdempotencji(meta.keyScope),
      }
      manualQueueAttemptRef.current = attempt
    }
    await runAction(
      'queue',
      (signal) => api(meta.queuePath(resolvedOwnerId), 'POST', null, {
        signal,
        headers: {
          'Idempotency-Key': attempt.key,
          ...(confirmResend ? { 'X-Confirm-Resend': 'true' } : {}),
        },
      }),
      meta.queueSuccess,
      {
        clearManualAttempt: true,
        onSuccess: () => setQueueCommitted(true),
      },
    )
  }

  const retry = (message) => runAction(
    actionKey('retry', message.id),
    (signal) => api(`/rezerwacje/komunikacja/${message.id}/retry`, 'POST', null, { signal }),
    'Ponowienie dodano do kolejki.',
  )

  const reconcile = (message, outcome) => {
    const note = (notes[message.id] || '').trim()
    if (note.length < 3) {
      setFeedback({ type: 'error', message: 'Dodaj krótką notatkę z wynikiem sprawdzenia.' })
      document.getElementById(`${panelId}-note-${message.id}`)?.focus()
      return
    }
    const labels = {
      sent: isStaleDelivered(message)
        ? 'Alert zamknięty. Dostarczenie pozostaje zapisane w historii.'
        : 'Wiadomość oznaczono jako wysłaną.',
      failed: 'Wiadomość oznaczono jako niewysłaną.',
      retry: 'Ponowienie dodano do kolejki ze świadomą zgodą na ryzyko duplikatu.',
    }
    void runAction(
      actionKey(`reconcile-${outcome}`, message.id),
      (signal) => api(
        `/rezerwacje/komunikacja/${message.id}/reconcile`,
        'POST',
        { wynik: outcome, notatka: note },
        { signal },
      ),
      labels[outcome],
    )
  }

  const contactDisabled = !canQueue || communicationPreference === 'brak'
  const queueDisabled = actionsDisabled || visibleLoading || Boolean(loadError) || contactDisabled || Boolean(manualBlockReason)
  const queueDisabledReason = actionsDisabled
    ? meta.disabledChangesLabel
    : visibleLoading
      ? 'Poczekaj na sprawdzenie historii komunikacji.'
      : loadError
        ? 'Najpierw ponów odczyt historii, aby bezpiecznie uniknąć podwójnej wiadomości.'
        : manualBlockReason
          || (communicationPreference === 'brak'
            ? 'Włącz kanał komunikacji, aby wysyłać wiadomości.'
            : !canQueue
              ? 'Dodaj e-mail lub telefon gościa, aby wysłać wiadomość.'
              : null)
  const queueLabel = ownerType === 'reservation' && hasManualMessage ? meta.resendLabel : meta.queueLabel

  return (
    <section className="mt-5 min-w-0 border-t border-line pt-5" aria-labelledby={`${panelId}-title`} aria-busy={visibleLoading || refreshing}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h4 id={`${panelId}-title`} className="text-sm font-semibold text-ink">Komunikacja z gościem</h4>
          <p className="mt-1 text-xs leading-relaxed text-muted">{meta.help}</p>
        </div>
        {visibleLoading && !visibleHistory.summary ? (
          <span className="inline-flex min-h-7 items-center gap-2 text-xs text-muted" role="status">
            <Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Pobieram status…
          </span>
        ) : (
          <ReservationCommunicationStatus summary={visibleHistory.summary} live />
        )}
      </div>

      {loadError ? (
        <div role="alert">
          <Banner variant="warn" className="mt-4">
            <div className="flex flex-wrap items-center gap-3">
              <span>{loadError}</span>
              <Button variant="ghost" size="sm" onClick={() => load()}>Ponów odczyt</Button>
            </div>
          </Banner>
        </div>
      ) : null}

      {!visibleLoading && !loadError ? (
        <div className="mt-4 border-y border-line">
          {visibleHistory.messages.length ? visibleHistory.messages.map((message) => {
            const timestamp = formatTimestamp(message.sent_at || message.uncertain_at || message.updated_at || message.created_at)
            const busy = action?.endsWith(`:${message.id}`)
            const staleDelivered = isStaleDelivered(message)
            return (
              <article key={message.id} className="py-3 [&+&]:border-t [&+&]:border-line">
                <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
                  <div className="min-w-[10rem] flex-1">
                    <p className="text-sm font-semibold text-ink">{message.event_label || 'Wiadomość operacyjna'}</p>
                    <p className="mt-1 break-words text-xs leading-relaxed text-muted">
                      {CHANNEL_LABELS[message.channel] || message.channel || 'Kanał nieznany'}
                      {message.recipient ? ` · ${message.recipient}` : ''}
                      {timestamp ? ` · ${timestamp}` : ''}
                    </p>
                    <p className="mt-1 break-words text-xs text-muted">
                      Próby: {Number(message.attempt_count) || 0}/{Number(message.max_attempts) || 0}
                      {message.last_error_code ? ` · Kod: ${message.last_error_code}` : ''}
                    </p>
                  </div>
                  <ReservationCommunicationStatus summary={message} showChannel={false} />
                </div>

                {message.state === 'failed' && message.retry_allowed !== false ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-3"
                    onClick={() => retry(message)}
                    loading={action === actionKey('retry', message.id)}
                    loadingLabel="Dodaję ponowienie…"
                    disabled={Boolean(action) || actionsDisabled}
                  >
                    <Icon name="refresh" className="h-4 w-4" />
                    Ponów
                  </Button>
                ) : null}

                {message.state === 'failed' && message.retry_allowed === false ? (
                  <p className="mt-3 text-xs leading-relaxed text-muted">
                    Ta wiadomość dotyczy wcześniejszej wersji rezerwacji i nie można jej ponowić.
                  </p>
                ) : null}

                {message.state === 'uncertain' ? (
                  <div className="mt-3 border-y border-lemon/25 bg-lemon/[0.04] px-3 py-3" role="note" aria-label="Niepewny wynik dostarczenia">
                    <div className="flex gap-2 text-sm leading-relaxed text-lemon">
                      <Icon name="warning" className="mt-0.5 h-4 w-4 shrink-0" />
                      <p>
                        {staleDelivered
                          ? 'Wiadomość została dostarczona po wycofaniu, anulowaniu lub wygaśnięciu oferty. Gość mógł zobaczyć nieaktualną informację o gotowym stoliku.'
                          : 'Dostawca mógł przyjąć wiadomość. Sprawdź skrzynkę lub panel dostawcy — ponowienie może wysłać duplikat.'}
                      </p>
                    </div>
                    <label htmlFor={`${panelId}-note-${message.id}`} className="field-label mt-3 block">
                      {staleDelivered ? 'Sposób wyjaśnienia' : 'Wynik sprawdzenia'}
                      <textarea
                        id={`${panelId}-note-${message.id}`}
                        rows={2}
                        maxLength={500}
                        value={notes[message.id] || ''}
                        onChange={(event) => setNotes((current) => ({ ...current, [message.id]: event.target.value }))}
                        className="field mt-1.5 resize-y"
                        placeholder={staleDelivered
                          ? 'np. Telefonicznie wyjaśniono gościowi zmianę'
                          : 'np. Brak wiadomości w panelu SMS'}
                        disabled={Boolean(action) || actionsDisabled}
                      />
                    </label>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {staleDelivered ? (
                        <Button size="sm" variant="ghost" disabled={Boolean(action) || actionsDisabled} loading={action === actionKey('reconcile-sent', message.id)} loadingLabel="Zamykam alert…" onClick={() => reconcile(message, 'sent')}>
                          <Icon name="check" className="h-4 w-4" />
                          Potwierdź i zamknij alert
                        </Button>
                      ) : (
                        <>
                          <Button size="sm" variant="ghost" disabled={Boolean(action) || actionsDisabled} loading={action === actionKey('reconcile-sent', message.id)} loadingLabel="Zapisuję…" onClick={() => reconcile(message, 'sent')}>
                            <Icon name="check" className="h-4 w-4" />
                            Oznacz jako wysłaną
                          </Button>
                          <Button size="sm" variant="ghost" disabled={Boolean(action) || actionsDisabled} loading={action === actionKey('reconcile-failed', message.id)} loadingLabel="Zapisuję…" onClick={() => reconcile(message, 'failed')}>
                            <Icon name="close" className="h-4 w-4" />
                            Oznacz jako niewysłaną
                          </Button>
                          {message.retry_allowed !== false ? (
                            <Button size="sm" variant="ghost" className="border-danger/25 text-danger hover:bg-danger/10" disabled={Boolean(action) || actionsDisabled} loading={action === actionKey('reconcile-retry', message.id)} loadingLabel="Dodaję ponowienie…" onClick={() => reconcile(message, 'retry')}>
                              <Icon name="refresh" className="h-4 w-4" />
                              Ponów mimo ryzyka
                            </Button>
                          ) : null}
                        </>
                      )}
                    </div>
                    {!staleDelivered && message.retry_allowed === false ? (
                      <p className="mt-2 text-xs leading-relaxed text-muted">
                        To wynik wcześniejszej wersji rezerwacji. Możesz go oznaczyć, ale nie ponawiać wysyłki.
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {busy ? <span className="sr-only" role="status">Trwa zapisywanie statusu wiadomości.</span> : null}
              </article>
            )
          }) : (
            <p className="py-4 text-sm text-muted">
              {communicationPreference === 'brak'
                ? 'Komunikacja operacyjna jest wyłączona dla tego wpisu.'
                : meta.emptyLabel}
            </p>
          )}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {showQueueAction ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={queueMessage}
            loading={action === 'queue' || action === 'queue-confirm'}
            loadingLabel={action === 'queue-confirm' ? 'Czekam na decyzję…' : 'Dodaję do kolejki…'}
            disabled={Boolean(action) || queueDisabled}
          >
            <Icon name="bell" className="h-4 w-4" />
            {queueLabel}
          </Button>
        ) : null}
        {refreshing ? <span className="inline-flex items-center gap-2 text-xs text-muted" role="status"><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Aktualizuję…</span> : null}
      </div>
      {showQueueAction && queueDisabledReason ? <p className="mt-2 text-xs leading-relaxed text-muted">{queueDisabledReason}</p> : null}
      <InlineFeedback
        feedback={refreshError ? { type: 'warning', message: `Nie udało się odświeżyć statusu: ${refreshError}` } : null}
        className="mt-2"
      />
      <InlineFeedback feedback={feedback} className="mt-1" />
    </section>
  )
}
