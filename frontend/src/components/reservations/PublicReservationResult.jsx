import { formatReservationDate } from '../../lib/publicReservation'
import { Icon } from '../../lib/icons'
import PublicReservationPayment from './PublicReservationPayment'

const ACTIVE_STATUSES = new Set(['rezerwacja', 'potwierdzona'])

export default function PublicReservationResult({
  headingRef,
  result,
  kind,
  cancelling,
  cancelError,
  paymentBusy,
  paymentError,
  onCancel,
  onRetryPayment,
  onNewReservation,
}) {
  const reservation = result.rezerwacja || result.wpis || {}
  const status = reservation.status
  const cancelled = status === 'odwolana'
  const waitlist = kind === 'waitlist'
  const payment = result.platnosc
  const paymentPending = !waitlist && ['oczekuje', 'nieudana', 'wygasla'].includes(payment?.status)
  const paymentDone = ['autoryzowana', 'oplacona'].includes(payment?.status)
  const title = cancelled
    ? 'Rezerwacja odwołana'
    : waitlist
      ? 'Jesteś na liście oczekujących'
      : paymentPending
        ? 'Dokończ rezerwację'
        : status === 'potwierdzona'
          ? 'Rezerwacja potwierdzona'
          : 'Rezerwacja przyjęta'

  return (
    <section className="text-center" aria-labelledby="public-reservation-result-title">
      <div
        className={`mx-auto mb-5 grid h-14 w-14 place-items-center rounded-full ${cancelled ? 'bg-danger/10 text-danger' : paymentPending ? 'bg-white/[0.06] text-ink' : 'bg-mint/15 text-mint'}`}
        aria-hidden="true"
      >
        <Icon name={cancelled ? 'close' : paymentPending ? 'clock' : 'check'} className="h-7 w-7" strokeWidth={1.8} />
      </div>
      <h2
        ref={headingRef}
        id="public-reservation-result-title"
        tabIndex="-1"
        className="font-display text-xl font-semibold tracking-tight text-ink outline-none"
      >
        {title}
      </h2>
      <p className="mx-auto mt-3 max-w-sm text-base leading-relaxed text-muted">
        {waitlist
          ? 'Lokal skontaktuje się z Tobą, gdy pojawi się miejsce pasujące do zgłoszenia.'
          : cancelled
            ? 'Termin został zwolniony. W każdej chwili możesz wyszukać nowy.'
            : paymentPending
              ? 'Termin jest zapisany. Dokończ bezpieczną płatność, aby spełnić politykę lokalu.'
              : paymentDone
                ? 'Płatność została potwierdzona. Dane wizyty są widoczne poniżej.'
                : status === 'rezerwacja'
                  ? 'Lokal potwierdzi rezerwację. Dane wizyty są widoczne poniżej.'
                  : 'Miejsce czeka na Ciebie. Dane wizyty są widoczne poniżej.'}
      </p>

      <dl className="mt-6 divide-y divide-line border-y border-line text-left text-sm">
        <div className="flex min-h-12 items-center justify-between gap-4 py-3">
          <dt className="text-muted">Termin</dt>
          <dd className="text-right font-medium text-ink capitalize">
            {formatReservationDate(reservation.data)}{reservation.godz_od ? `, ${reservation.godz_od}` : ''}
          </dd>
        </div>
        <div className="flex min-h-12 items-center justify-between gap-4 py-3">
          <dt className="text-muted">Goście</dt>
          <dd className="font-medium text-ink">{reservation.liczba_osob} os.</dd>
        </div>
        {reservation.nazwisko ? (
          <div className="flex min-h-12 items-center justify-between gap-4 py-3">
            <dt className="text-muted">Rezerwacja dla</dt>
            <dd className="text-right font-medium text-ink">{reservation.nazwisko}</dd>
          </div>
        ) : null}
      </dl>

      {!waitlist ? (
        <PublicReservationPayment
          payment={payment}
          busy={paymentBusy}
          error={paymentError}
          onRetry={onRetryPayment}
        />
      ) : null}

      {cancelError ? (
        <div className="mt-5 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-left" role="alert">
          <p className="text-sm text-danger">{cancelError}</p>
        </div>
      ) : null}

      {!waitlist && (result.management_available || result.management_token) && ACTIVE_STATUSES.has(status) ? (
        <button
          type="button"
          onClick={onCancel}
          disabled={cancelling}
          className="mt-6 min-h-12 w-full rounded-xl border border-line bg-white/[0.025] px-4 py-3 text-sm font-semibold text-ink transition ease-snap hover:border-danger/40 hover:bg-danger/[0.08] active:scale-[0.98] disabled:cursor-wait disabled:opacity-50"
        >
          {cancelling ? 'Odwołuję…' : 'Odwołaj rezerwację'}
        </button>
      ) : null}

      <button
        type="button"
        onClick={onNewReservation}
        disabled={cancelling}
        className="mt-3 min-h-12 w-full rounded-xl px-4 py-3 text-sm font-semibold text-muted transition hover:bg-white/[0.04] hover:text-ink active:scale-[0.98] disabled:opacity-50"
      >
        Wyszukaj nowy termin
      </button>
    </section>
  )
}
