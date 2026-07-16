import { Icon } from '../../lib/icons'

const money = (payment) => {
  const minor = Number(payment?.amount_minor ?? payment?.kwota_minor)
  if (Number.isFinite(minor)) {
    return new Intl.NumberFormat('pl-PL', {
      style: 'currency',
      currency: String(payment?.currency || 'PLN').toUpperCase(),
    }).format(minor / 100)
  }
  const amount = Number(payment?.kwota)
  return Number.isFinite(amount) ? `${amount.toFixed(2).replace('.', ',')} zł` : null
}

export default function PublicReservationPayment({ payment, busy, error, onRetry }) {
  if (!payment || payment.status === 'niewymagana') return null

  const kind = payment.kind || payment.rodzaj || 'deposit'
  const status = payment.status
  const link = payment.checkout_url || payment.link
  const amount = money(payment)
  const preauth = ['preauth', 'preauthorization', 'preautoryzacja'].includes(kind)
  const pending = status === 'oczekuje'
  const failed = status === 'nieudana' || status === 'wygasla'
  const refundPending = payment.refund_status === 'oczekuje'
  const demo = Boolean(payment.tryb_demo)

  let title = preauth ? 'Potwierdź kartę' : 'Opłać zadatek'
  let description = preauth
    ? 'Bank zablokuje kwotę, ale lokal nie pobierze jej teraz.'
    : 'Rezerwacja zostanie domknięta po potwierdzeniu płatności przez operatora.'
  let icon = 'clock'
  let tone = 'border-line bg-white/[0.025]'

  if (refundPending) {
    title = 'Zwrot jest przetwarzany'
    description = 'Rezerwacja jest odwołana. Potwierdzenie zwrotu pojawi się tutaj po odpowiedzi operatora płatności.'
    icon = 'clock'
    tone = 'border-line bg-white/[0.025]'
  } else if (status === 'autoryzowana') {
    title = 'Kwota została zablokowana'
    description = 'Preautoryzacja jest aktywna. Środki nie zostały jeszcze pobrane.'
    icon = 'check'
    tone = 'border-mint/30 bg-mint/[0.08]'
  } else if (status === 'oplacona') {
    title = 'Zadatek opłacony'
    description = 'Płatność została potwierdzona. Nie musisz nic więcej robić.'
    icon = 'check'
    tone = 'border-mint/30 bg-mint/[0.08]'
  } else if (status === 'zwrocona') {
    title = 'Zadatek zwrócony'
    description = 'Zwrot został potwierdzony przez operatora płatności.'
    icon = 'check'
    tone = 'border-mint/30 bg-mint/[0.08]'
  } else if (failed) {
    title = status === 'wygasla' ? 'Link do płatności wygasł' : 'Płatność nie powiodła się'
    description = payment.failure_action === 'zwolnij' || payment.po_niepowodzeniu === 'zwolnij'
      ? 'Termin mógł zostać zwolniony zgodnie z polityką lokalu.'
      : 'Twoje dane są zachowane. Możesz bezpiecznie spróbować ponownie.'
    icon = 'warning'
    tone = 'border-danger/30 bg-danger/[0.08]'
  }

  return (
    <section className={`mt-6 rounded-2xl border p-4 text-left ${tone}`} aria-labelledby="public-payment-title">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white/[0.05] text-ink" aria-hidden="true">
          <Icon name={icon} className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h3 id="public-payment-title" className="font-semibold text-ink">{title}</h3>
            {amount ? <span className="font-mono text-sm font-semibold text-ink">{amount}</span> : null}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-muted">{description}</p>
        </div>
      </div>

      {pending && link ? (
        <a
          href={link}
          className="mt-4 flex min-h-12 w-full items-center justify-center rounded-xl bg-cream px-4 py-3 text-sm font-semibold text-bg shadow-cta transition ease-snap hover:bg-white active:scale-[0.98]"
        >
          {demo ? 'Otwórz płatność demonstracyjną' : 'Przejdź do bezpiecznej płatności'}
        </a>
      ) : null}

      {pending && !link ? (
        <p className="mt-4 text-sm font-medium text-ink" role="status">Przygotowuję bezpieczny link…</p>
      ) : null}

      {failed && (payment.can_retry ?? payment.mozna_ponowic ?? true) && !(payment.failure_action === 'zwolnij' || payment.po_niepowodzeniu === 'zwolnij') ? (
        <button
          type="button"
          onClick={onRetry}
          disabled={busy}
          className="mt-4 min-h-12 w-full rounded-xl border border-line bg-white/[0.04] px-4 py-3 text-sm font-semibold text-ink transition hover:bg-white/[0.08] active:scale-[0.98] disabled:cursor-wait disabled:opacity-50"
        >
          {busy ? 'Przygotowuję nowy link…' : 'Spróbuj ponownie'}
        </button>
      ) : null}

      {error ? <p className="mt-3 text-sm text-danger" role="alert">{error}</p> : null}
      <p className="mt-3 text-xs leading-relaxed text-muted">
        {demo
          ? 'Tryb demonstracyjny — żadne środki nie zostaną pobrane.'
          : 'Płatność obsługuje Stripe. Lokalo nie przechowuje danych karty.'}
      </p>
    </section>
  )
}
