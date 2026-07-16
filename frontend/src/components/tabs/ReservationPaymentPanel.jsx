import { useEffect, useMemo, useRef, useState } from 'react'
import { api, nowyKluczIdempotencji } from '../../lib/api'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { InlineFeedback } from '../ui/InlineFeedback'
import {
  PUBLIC_PAYMENT_POLL_DELAYS_MS,
  publicPaymentNeedsPolling,
} from '../../lib/publicPaymentPolling'

const STATUS = {
  oczekuje: { label: 'Oczekuje na płatność', icon: 'clock', tone: 'bg-lemon/10 text-lemon' },
  autoryzowana: { label: 'Kwota zablokowana', icon: 'check', tone: 'bg-mint/10 text-mint' },
  oplacona: { label: 'Opłacona', icon: 'check', tone: 'bg-mint/10 text-mint' },
  nieudana: { label: 'Nieudana', icon: 'warning', tone: 'bg-danger/10 text-danger' },
  wygasla: { label: 'Wygasła', icon: 'clock', tone: 'bg-white/[0.05] text-muted' },
  anulowana: { label: 'Anulowana', icon: 'close', tone: 'bg-white/[0.05] text-muted' },
  zwrocona: { label: 'Zwrócona', icon: 'check', tone: 'bg-white/[0.05] text-muted' },
}

const money = (minor, currency = 'PLN') => new Intl.NumberFormat('pl-PL', {
  style: 'currency',
  currency: String(currency || 'PLN').toUpperCase(),
}).format((Number(minor) || 0) / 100)

const PAYMENT_KIND_LABEL = {
  zadatek: 'Zadatek',
  preautoryzacja: 'Preautoryzacja',
  no_show: 'Opłata za nieobecność',
  reczna: 'Płatność ręczna',
}

const BLOCKING_COMMAND_STATES = new Set(['queued', 'processing', 'retry', 'uncertain'])
const POLLING_COMMAND_STATES = new Set(['queued', 'processing', 'retry'])
const FAILED_COMMAND_STATES = new Set(['failed', 'cancelled'])

const COMMAND_STATE = {
  queued: { label: 'Oczekuje w kolejce', tone: 'text-lemon' },
  processing: { label: 'Operacja w toku', tone: 'text-lemon' },
  retry: { label: 'Automatyczne ponowienie', tone: 'text-lemon' },
  uncertain: { label: 'Wymaga uzgodnienia', tone: 'text-danger' },
  succeeded: { label: 'Operacja zakończona', tone: 'text-success' },
  failed: { label: 'Operacja nieudana', tone: 'text-danger' },
  cancelled: { label: 'Operacja anulowana', tone: 'text-muted' },
}

const commandReachedProjection = (command, payment) => {
  if (!command || !payment || Number(command.platnosc_id) !== Number(payment.id)) return false
  if (command.typ === 'create_checkout') {
    return payment.status !== 'oczekuje' || Boolean(payment.link)
  }
  if (command.typ === 'capture') return payment.status !== 'autoryzowana'
  if (command.typ === 'cancel_authorization') {
    return !['oczekuje', 'autoryzowana'].includes(payment.status)
  }
  if (command.typ === 'refund') {
    return payment.status === 'zwrocona'
      || ['zwrocona', 'nieudana'].includes(payment.refund_status)
  }
  return false
}

const commandProgressMessage = (command) => {
  if (command?.stan === 'uncertain') {
    return 'Sprawdzamy wynik operacji. Nie zlecaj jej ponownie.'
  }
  if (command?.stan === 'retry') {
    return 'Operator płatności ponowi operację automatycznie.'
  }
  return {
    create_checkout: 'Przygotowanie nowego linku do płatności jest w toku.',
    capture: 'Pobranie kwoty jest w toku.',
    cancel_authorization: 'Zwalnianie blokady środków jest w toku.',
    refund: 'Zwrot środków jest w toku.',
    reconcile: 'Sprawdzanie płatności jest w toku.',
  }[command?.typ] || 'Operacja płatnicza jest w toku.'
}

const paymentOperationState = (payment) => {
  const command = payment?.latest_command || null
  const projectionReached = commandReachedProjection(command, payment)
  const commandBlocksActions = Boolean(
    command
    && BLOCKING_COMMAND_STATES.has(command.stan)
    && !projectionReached,
  )
  const commandNeedsPolling = Boolean(
    command
    && POLLING_COMMAND_STATES.has(command.stan)
    && !projectionReached,
  )
  const commandFailed = Boolean(
    command
    && FAILED_COMMAND_STATES.has(command.stan)
    && !projectionReached,
  )
  const commandUncertain = Boolean(
    command?.stan === 'uncertain'
    && !projectionReached,
  )
  const operationPending = commandBlocksActions || payment?.refund_status === 'oczekuje'
  const terminalCommandNeedsAttention = commandFailed || commandUncertain
  const providerManaged = ['stripe', 'sandbox'].includes(payment?.provider)

  return {
    command,
    commandBlocksActions,
    commandNeedsPolling,
    commandFailed,
    commandUncertain,
    operationPending,
    pollingNeeded: providerManaged && !terminalCommandNeedsAttention && (
      Boolean(payment && publicPaymentNeedsPolling(payment)) || commandNeedsPolling
    ),
    projectionReached,
  }
}

const commandRowMeta = (payment) => {
  const state = paymentOperationState(payment)
  if (!state.command) return null
  if (state.projectionReached) return { label: 'Stan potwierdzony', tone: 'text-muted' }
  return COMMAND_STATE[state.command.stan] || { label: 'Operacja zapisana', tone: 'text-muted' }
}

export default function ReservationPaymentPanel({
  reservationId,
  disabled = false,
  confirmAction,
  onManagedPaymentChange,
}) {
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [refreshError, setRefreshError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [action, setAction] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [selectedPaymentId, setSelectedPaymentId] = useState(null)
  const actionKeys = useRef(new Map())

  const selectedPayment = useMemo(() => (
    payments.find((payment) => Number(payment.id) === Number(selectedPaymentId))
    || payments[0]
    || null
  ), [payments, selectedPaymentId])
  const selectedOperation = useMemo(
    () => paymentOperationState(selectedPayment),
    [selectedPayment],
  )
  const pollingNeeded = useMemo(
    () => payments.some((payment) => paymentOperationState(payment).pollingNeeded),
    [payments],
  )

  useEffect(() => {
    onManagedPaymentChange?.(payments.length > 0)
  }, [onManagedPaymentChange, payments.length])

  useEffect(() => {
    if (!reservationId) {
      setPayments([])
      setLoading(false)
      setLoadError('')
      setRefreshError('')
      setRefreshing(false)
      setFeedback(null)
      setSelectedPaymentId(null)
      actionKeys.current.clear()
      return undefined
    }
    const controller = new AbortController()
    setPayments([])
    setLoading(true)
    setLoadError('')
    setRefreshError('')
    setRefreshing(false)
    setAction(null)
    setFeedback(null)
    setSelectedPaymentId(null)
    actionKeys.current.clear()
    api(`/platnosci?termin_id=${encodeURIComponent(reservationId)}`, 'GET', null, {
      signal: controller.signal,
    })
      .then((rows) => {
        const next = Array.isArray(rows) ? rows : []
        setPayments(next)
        setSelectedPaymentId(next[0]?.id ?? null)
      })
      .catch((error) => {
        if (error?.name !== 'AbortError') {
          setLoadError(error?.message || 'Nie udało się pobrać statusu płatności.')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [reservationId])

  useEffect(() => {
    if (!reservationId || loading || action || !pollingNeeded) {
      setRefreshing(false)
      return undefined
    }

    let disposed = false
    let timer = null
    let controller = null
    let inFlight = false
    let refreshAfterFlight = false
    let delayIndex = 0
    const visibilityTarget = globalThis.document

    const isVisible = () => !visibilityTarget || visibilityTarget.visibilityState !== 'hidden'
    const clearScheduled = () => {
      if (timer !== null) clearTimeout(timer)
      timer = null
    }

    const schedule = () => {
      if (disposed || inFlight || !isVisible()) return
      const delay = PUBLIC_PAYMENT_POLL_DELAYS_MS[
        Math.min(delayIndex, PUBLIC_PAYMENT_POLL_DELAYS_MS.length - 1)
      ]
      delayIndex += 1
      clearScheduled()
      timer = setTimeout(() => {
        timer = null
        void refresh()
      }, delay)
    }

    const refresh = async () => {
      if (disposed || inFlight || !isVisible()) return
      inFlight = true
      setRefreshing(true)
      controller = new AbortController()
      try {
        const rows = await api(
          `/platnosci?termin_id=${encodeURIComponent(reservationId)}`,
          'GET',
          null,
          { signal: controller.signal },
        )
        if (!disposed) {
          const next = Array.isArray(rows) ? rows : []
          setPayments(next)
          setSelectedPaymentId((current) => (
            next.some((payment) => Number(payment.id) === Number(current))
              ? current
              : next[0]?.id ?? null
          ))
          setRefreshError('')
        }
      } catch (error) {
        if (!disposed && error?.name !== 'AbortError') {
          setRefreshError('Nie udało się odświeżyć statusu. Spróbuję ponownie automatycznie.')
        }
      } finally {
        inFlight = false
        controller = null
        if (!disposed) {
          setRefreshing(false)
          if (refreshAfterFlight && isVisible()) {
            refreshAfterFlight = false
            void refresh()
          } else {
            schedule()
          }
        }
      }
    }

    const onVisibilityChange = () => {
      clearScheduled()
      if (!isVisible()) {
        controller?.abort()
        return
      }
      delayIndex = 0
      if (inFlight) {
        refreshAfterFlight = true
      } else {
        void refresh()
      }
    }

    visibilityTarget?.addEventListener?.('visibilitychange', onVisibilityChange)
    schedule()

    return () => {
      disposed = true
      refreshAfterFlight = false
      clearScheduled()
      controller?.abort()
      visibilityTarget?.removeEventListener?.('visibilitychange', onVisibilityChange)
    }
  }, [action, loading, pollingNeeded, reservationId])

  const run = async (payment, kind, path, body, message) => {
    if (!payment || action || disabled) return
    const keyRef = `${payment.id}:${kind}`
    if (!actionKeys.current.has(keyRef)) {
      actionKeys.current.set(keyRef, nowyKluczIdempotencji(`reservation-payment-${kind}`))
    }
    setAction({ paymentId: payment.id, kind })
    setFeedback(null)
    try {
      const response = await api(path, 'POST', body, {
        headers: { 'Idempotency-Key': actionKeys.current.get(keyRef) },
      })
      const updatedPayment = response?.payment || response
      const responseCommand = response?.command || updatedPayment?.latest_command || null
      setPayments((current) => {
        const existing = current.find((item) => Number(item.id) === Number(updatedPayment.id))
        const projected = {
          ...existing,
          ...updatedPayment,
          latest_command: responseCommand || existing?.latest_command || null,
        }
        if (!existing) return [projected, ...current]
        return current.map((item) => (
          Number(item.id) === Number(projected.id) ? projected : item
        ))
      })
      setSelectedPaymentId(updatedPayment.id)
      actionKeys.current.delete(keyRef)
      setFeedback({ paymentId: updatedPayment.id, type: 'success', message })
    } catch (error) {
      if (error?.code === 'PAYMENT_OPERATION_KEY_REUSED') actionKeys.current.delete(keyRef)
      setFeedback({
        paymentId: payment.id,
        type: 'error',
        message: error?.message || 'Nie udało się wykonać operacji.',
      })
    } finally {
      setAction(null)
    }
  }

  const approveAndRun = async ({ payment, kind, title, prompt, path, body, message }) => {
    const approved = await confirmAction?.(prompt, {
      title,
      confirmText: title,
      cancelText: 'Wróć',
    })
    if (!approved) return
    await run(payment, kind, path, body, message)
  }

  const markManualPaid = async (payment) => {
    if (!payment || action || disabled) return
    setAction({ paymentId: payment.id, kind: 'paid' })
    setFeedback(null)
    try {
      const updatedPayment = await api(`/platnosci/${payment.id}/oplacona`, 'POST')
      setPayments((current) => current.map((item) => (
        Number(item.id) === Number(updatedPayment.id)
          ? {
            ...item,
            ...updatedPayment,
            latest_command: updatedPayment.latest_command || item.latest_command || null,
          }
          : item
      )))
      setFeedback({
        paymentId: updatedPayment.id,
        type: 'success',
        message: payment.provider === 'ledger'
          ? 'Oznaczono należność jako rozliczoną.'
          : 'Oznaczono płatność demonstracyjną jako opłaconą.',
      })
    } catch (error) {
      setFeedback({
        paymentId: payment.id,
        type: 'error',
        message: error?.message || 'Nie udało się potwierdzić płatności.',
      })
    } finally {
      setAction(null)
    }
  }

  const meta = selectedPayment ? (STATUS[selectedPayment.status] || STATUS.oczekuje) : null
  const busy = Boolean(action)
  const selectedAction = Number(action?.paymentId) === Number(selectedPayment?.id) ? action?.kind : null
  const actionsDisabled = disabled || busy || selectedOperation.operationPending
  const retryAllowed = selectedPayment?.can_retry ?? selectedPayment?.mozna_ponowic
  const visibleFeedback = Number(feedback?.paymentId) === Number(selectedPayment?.id)
    ? feedback
    : null

  return (
    <section className="mt-5 border-t border-line pt-5" aria-labelledby="reservation-payment-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h4 id="reservation-payment-heading" className="text-sm font-semibold text-ink">
            {payments.length > 1 ? 'Płatności rezerwacji' : 'Płatność rezerwacji'}
          </h4>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {payments.length > 1
              ? 'Wybierz pozycję, aby sprawdzić jej stan i dostępne działania.'
              : 'Stan potwierdza operator płatności, nie sam powrót klienta.'}
          </p>
        </div>
        {payments.length > 1 ? (
          <span className="inline-flex min-h-8 items-center rounded-full bg-white/[0.05] px-2.5 py-1 text-xs font-semibold text-muted">
            {payments.length} {payments.length < 5 ? 'pozycje' : 'pozycji'}
          </span>
        ) : meta ? (
          <span className={`inline-flex min-h-8 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${meta.tone}`}>
            <Icon name={meta.icon} className="h-3.5 w-3.5" />
            {meta.label}
          </span>
        ) : null}
      </div>

      {loading ? <p className="mt-4 text-sm text-muted" role="status">Sprawdzam płatność…</p> : null}
      {loadError ? <p className="mt-4 text-sm text-danger" role="alert">{loadError}</p> : null}
      {!loading && !loadError && !selectedPayment ? (
        <p className="mt-4 rounded-xl bg-white/[0.025] px-3 py-3 text-sm text-muted">Ta rezerwacja nie wymaga płatności online.</p>
      ) : null}

      {selectedPayment ? (
        <div className="mt-4 overflow-hidden rounded-xl border border-line bg-white/[0.025]">
          {payments.length > 1 ? (
            <div className="divide-y divide-line" role="radiogroup" aria-label="Płatności rezerwacji">
              {payments.map((payment) => {
                const paymentMeta = STATUS[payment.status] || STATUS.oczekuje
                const operationMeta = commandRowMeta(payment)
                const isSelected = Number(payment.id) === Number(selectedPayment.id)
                const kindLabel = PAYMENT_KIND_LABEL[payment.rodzaj] || 'Płatność'
                return (
                  <button
                    key={payment.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    aria-label={`${kindLabel}, ${money(payment.kwota_minor, payment.waluta)}, ${paymentMeta.label}${operationMeta ? `, ${operationMeta.label}` : ''}`}
                    onClick={() => setSelectedPaymentId(payment.id)}
                    className={`flex min-h-14 w-full items-center justify-between gap-3 px-3.5 py-3 text-left transition duration-150 ease-snap active:bg-white/[0.08] ${isSelected ? 'bg-mint/[0.09]' : 'hover:bg-white/[0.05]'}`}
                  >
                    <span className="min-w-0">
                      <span className={`block text-sm font-semibold ${isSelected ? 'text-mint' : 'text-ink'}`}>
                        {kindLabel}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                        <span className={paymentMeta.tone.split(' ').at(-1)}>{paymentMeta.label}</span>
                        {operationMeta ? <span className={operationMeta.tone}>· {operationMeta.label}</span> : null}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-sm font-semibold text-ink">
                      {money(payment.kwota_minor, payment.waluta)}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : null}

          <div className={`p-3.5 ${payments.length > 1 ? 'border-t border-line' : ''}`}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">
                  {PAYMENT_KIND_LABEL[selectedPayment.rodzaj] || 'Płatność'}
                </p>
                {payments.length > 1 && meta ? (
                  <span className={`mt-1 inline-flex min-h-7 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold ${meta.tone}`}>
                    <Icon name={meta.icon} className="h-3.5 w-3.5" />
                    {meta.label}
                  </span>
                ) : null}
              </div>
              <p className="shrink-0 font-mono text-sm font-semibold text-ink">
                {money(selectedPayment.kwota_minor, selectedPayment.waluta)}
              </p>
            </div>
            {selectedPayment.refund_status === 'oczekuje' ? <p className="mt-2 text-xs text-lemon">Zwrot jest przetwarzany.</p> : null}
            {selectedPayment.status === 'autoryzowana' ? <p className="mt-2 text-xs text-muted">Środki są tylko zablokowane. Pobranie wymaga jawnego potwierdzenia.</p> : null}
            {selectedOperation.operationPending ? (
              <div className="mt-3 flex items-start gap-2 text-sm text-lemon" role="status" aria-live="polite">
                <Icon name={selectedOperation.commandUncertain ? 'warning' : 'clock'} className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0">
                  <p className="font-medium text-ink">
                    {selectedOperation.commandUncertain ? 'Wymaga uzgodnienia' : 'Operacja w toku'}
                  </p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">
                    {selectedOperation.commandUncertain
                      ? 'Operator nie potwierdził wyniku. Sprawdzenie odczyta stan lub bezpiecznie wznowi pierwotne zlecenie z tym samym kluczem — bez drugiego obciążenia.'
                      : selectedOperation.commandBlocksActions
                        ? commandProgressMessage(selectedOperation.command)
                        : 'Zwrot środków jest przetwarzany.'}
                    {!selectedOperation.commandUncertain ? ' Status odświeży się automatycznie.' : ''}
                  </p>
                  {selectedOperation.commandUncertain ? (
                    <Button
                      size="sm"
                      className="mt-3"
                      onClick={() => approveAndRun({
                        payment: selectedPayment,
                        kind: 'reconcile',
                        title: 'Sprawdź stan',
                        prompt: 'Sprawdzić aktualny stan u operatora płatności? System użyje tego samego klucza operacji, więc nie utworzy drugiego obciążenia ani zwrotu.',
                        path: `/platnosci/${selectedPayment.id}/reconcile`,
                        body: { powod: 'operator_reconcile' },
                        message: 'Zlecono sprawdzenie stanu u operatora płatności.',
                      })}
                      loading={selectedAction === 'reconcile'}
                      loadingLabel="Zlecam sprawdzenie…"
                      disabled={disabled || busy}
                    >
                      <Icon name="refresh" className="h-4 w-4" />
                      Sprawdź stan u operatora
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}
            {selectedOperation.commandFailed ? (
              <p className="mt-3 rounded-xl border border-danger/20 bg-danger/[0.06] px-3 py-2.5 text-xs leading-relaxed text-danger" role="alert">
                Operacja nie została wykonana. Sprawdź stan płatności i spróbuj ponownie.
              </p>
            ) : null}

            <div className="mt-3 flex flex-wrap gap-2">
            {selectedPayment.status === 'oczekuje' && selectedPayment.link && !actionsDisabled ? (
              <a
                href={selectedPayment.link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-ink transition hover:bg-white/[0.08]"
              >
                <Icon name="upload" className="h-4 w-4" />
                Otwórz bezpieczny link
              </a>
            ) : null}
            {['sandbox', 'ledger'].includes(selectedPayment.provider) && selectedPayment.status === 'oczekuje' ? (
              <Button size="sm" onClick={() => markManualPaid(selectedPayment)} loading={selectedAction === 'paid'} loadingLabel="Potwierdzam…" disabled={actionsDisabled}>
                <Icon name="check" className="h-4 w-4" />
                {selectedPayment.provider === 'ledger' ? 'Oznacz jako rozliczoną' : 'Potwierdź demo'}
              </Button>
            ) : null}
            {selectedPayment.status === 'autoryzowana' ? (
              <>
                <Button
                  size="sm"
                  onClick={() => approveAndRun({
                    payment: selectedPayment,
                    kind: 'capture',
                    title: 'Pobierz kwotę',
                    prompt: `Pobrać ${money(selectedPayment.kwota_minor, selectedPayment.waluta)} z aktywnej preautoryzacji?`,
                    path: `/platnosci/${selectedPayment.id}/capture`,
                    body: { powod: 'operator_capture' },
                    message: 'Zlecono pobranie środków.',
                  })}
                  loading={selectedAction === 'capture'}
                  loadingLabel="Zlecam pobranie…"
                  disabled={actionsDisabled}
                >Pobierz kwotę</Button>
                <Button
                  variant="subtle"
                  size="sm"
                  onClick={() => approveAndRun({
                    payment: selectedPayment,
                    kind: 'cancel',
                    title: 'Zwolnij blokadę',
                    prompt: 'Zwolnić preautoryzację bez pobierania środków?',
                    path: `/platnosci/${selectedPayment.id}/anuluj-autoryzacje`,
                    body: { powod: 'operator_cancel' },
                    message: 'Zlecono zwolnienie blokady.',
                  })}
                  loading={selectedAction === 'cancel'}
                  loadingLabel="Zlecam zwolnienie…"
                  disabled={actionsDisabled}
                >Zwolnij blokadę</Button>
              </>
            ) : null}
            {['stripe', 'sandbox'].includes(selectedPayment.provider) && selectedPayment.status === 'oplacona' && selectedPayment.refund_status !== 'oczekuje' ? (
              <Button
                variant="subtle"
                size="sm"
                onClick={() => approveAndRun({
                  payment: selectedPayment,
                  kind: 'refund',
                  title: 'Zwróć zadatek',
                  prompt: `Zwrócić klientowi pełną pozostałą kwotę ${money((selectedPayment.przechwycono_minor || selectedPayment.kwota_minor) - (selectedPayment.zwrocono_minor || 0), selectedPayment.waluta)}?`,
                  path: `/platnosci/${selectedPayment.id}/zwrot`,
                  body: { powod: 'requested_by_customer' },
                  message: 'Zlecono pełny zwrot.',
                })}
                loading={selectedAction === 'refund'}
                loadingLabel="Zlecam zwrot…"
                disabled={actionsDisabled}
                className="border-danger/25 text-danger hover:bg-danger/10"
              >Zwróć zadatek</Button>
            ) : null}
            {['nieudana', 'wygasla'].includes(selectedPayment.status) && retryAllowed ? (
              <Button
                size="sm"
                onClick={() => run(
                  selectedPayment,
                  'retry',
                  `/platnosci/${selectedPayment.id}/retry`,
                  null,
                  'Przygotowywany jest nowy link do płatności.',
                )}
                loading={selectedAction === 'retry'}
                loadingLabel="Przygotowuję…"
                disabled={actionsDisabled}
              >Ponów płatność</Button>
            ) : null}
            </div>
            {pollingNeeded && !selectedOperation.operationPending ? (
              <p className="mt-3 text-xs text-muted" aria-hidden="true">
                {refreshing ? 'Aktualizuję status…' : 'Status odświeża się automatycznie.'}
              </p>
            ) : null}
            {refreshError ? <p className="mt-2 text-xs text-lemon" role="status">{refreshError}</p> : null}
          </div>
        </div>
      ) : null}

      <InlineFeedback pending={busy ? 'Zapisuję operację płatniczą…' : null} feedback={visibleFeedback} className="mt-3" />
    </section>
  )
}
