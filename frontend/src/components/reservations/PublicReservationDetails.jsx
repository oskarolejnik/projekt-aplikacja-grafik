import PublicReservationHold from './PublicReservationHold'
import { formatReservationDate } from '../../lib/publicReservation'

const describedBy = (error, id) => (error ? id : undefined)

export default function PublicReservationDetails({
  headingRef,
  mode,
  selection,
  form,
  config,
  errors,
  submitError,
  busy,
  holdRemaining,
  holdExpired,
  onChange,
  onBack,
  onChooseAnother,
  onSubmit,
}) {
  const isWaitlist = mode === 'waitlist'
  const sensitiveProvided = Boolean(form.sensitive_data.trim())

  return (
    <section aria-labelledby="public-reservation-details-title">
      <button
        type="button"
        onClick={onBack}
        disabled={busy}
        className="-ml-2 mb-3 inline-flex min-h-11 items-center rounded-xl px-2 text-sm font-semibold text-muted transition hover:text-ink active:scale-[0.98] disabled:opacity-50"
      >
        <span aria-hidden="true">←</span>&nbsp; Zmień termin
      </button>

      <h2
        ref={headingRef}
        id="public-reservation-details-title"
        tabIndex="-1"
        className="font-display text-xl font-semibold tracking-tight text-ink outline-none"
      >
        {isWaitlist ? 'Lista oczekujących' : 'Dokończ rezerwację'}
      </h2>
      <p className="mt-2 text-base leading-relaxed text-muted">
        {isWaitlist
          ? 'Zostaw dane. Lokal skontaktuje się z Tobą, jeśli zwolni się miejsce.'
          : 'Uzupełnij dane gościa. Twój szkic pozostanie na ekranie, jeśli coś pójdzie nie tak.'}
      </p>

      <div className="mt-5 border-y border-line py-4 text-sm text-ink">
        <span className="capitalize">{formatReservationDate(selection.data)}</span>
        {selection.godz_od ? <> · <strong>{selection.godz_od}</strong></> : null}
        {' · '}{selection.liczba_osob} os.
      </div>

      {!isWaitlist && holdRemaining !== null && !holdExpired ? (
        <PublicReservationHold remainingSeconds={holdRemaining} />
      ) : null}

      {holdExpired ? (
        <div className="mt-5 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3" role="alert">
          <p className="text-sm font-semibold text-danger">Czas na dokończenie rezerwacji minął.</p>
          <p className="mt-1 text-sm text-muted">Twoje dane zostały zachowane. Wybierz nową godzinę, aby kontynuować.</p>
          <button
            type="button"
            onClick={onChooseAnother}
            className="mt-3 min-h-11 rounded-xl border border-danger/30 px-4 text-sm font-semibold text-ink transition hover:bg-white/[0.05] active:scale-[0.98]"
          >
            Wybierz inną godzinę
          </button>
        </div>
      ) : null}

      <form className="mt-6 space-y-5" onSubmit={onSubmit} noValidate>
        {isWaitlist ? (
          <label className="block text-sm font-medium text-ink">
            Preferowana godzina <span className="font-normal text-muted">(opcjonalnie)</span>
            <input
              type="time"
              value={form.waitlist_time}
              onChange={(event) => onChange('waitlist_time', event.target.value)}
              className="field mt-2 min-h-12"
            />
          </label>
        ) : null}

        <label className="block text-sm font-medium text-ink">
          Imię i nazwisko
          <input
            value={form.nazwisko}
            onChange={(event) => onChange('nazwisko', event.target.value)}
            className="field mt-2 min-h-12"
            autoComplete="name"
            required
            aria-invalid={Boolean(errors.nazwisko)}
            aria-describedby={describedBy(errors.nazwisko, 'public-reservation-name-error')}
          />
          {errors.nazwisko ? <span id="public-reservation-name-error" className="mt-1 block text-sm text-danger">{errors.nazwisko}</span> : null}
        </label>

        <div>
          <p className="text-sm font-medium text-ink">Dane kontaktowe</p>
          <p className="mt-1 text-sm text-muted">Podaj telefon lub e-mail, aby lokal mógł potwierdzić szczegóły.</p>
        </div>

        <div data-testid="reservation-contact-fields" className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-ink">
            Telefon
            <input
              type="tel"
              inputMode="tel"
              value={form.telefon}
              onChange={(event) => onChange('telefon', event.target.value)}
              className="field mt-2 min-h-12"
              autoComplete="tel"
              aria-invalid={Boolean(errors.contact)}
              aria-describedby={describedBy(errors.contact, 'public-reservation-contact-error')}
            />
          </label>
          <label className="block text-sm font-medium text-ink">
            E-mail
            <input
              type="email"
              inputMode="email"
              value={form.email}
              onChange={(event) => onChange('email', event.target.value)}
              className="field mt-2 min-h-12"
              autoComplete="email"
              aria-invalid={Boolean(errors.email || errors.contact)}
              aria-describedby={errors.email
                ? 'public-reservation-email-error'
                : describedBy(errors.contact, 'public-reservation-contact-error')}
            />
            {errors.email ? <span id="public-reservation-email-error" className="mt-1 block text-sm text-danger">{errors.email}</span> : null}
          </label>
        </div>
        {errors.contact ? <p id="public-reservation-contact-error" className="-mt-3 text-sm text-danger">{errors.contact}</p> : null}

        <label className="block text-sm font-medium text-ink">
          Uwagi organizacyjne <span className="font-normal text-muted">(opcjonalnie)</span>
          <textarea
            rows="3"
            value={form.notatka}
            onChange={(event) => onChange('notatka', event.target.value)}
            className="field mt-2 min-h-24 resize-y"
            placeholder="Np. wózek dziecięcy lub miejsce przy wejściu"
          />
        </label>

        <div className="border-t border-line pt-5">
          <label className="block text-sm font-medium text-ink">
            Alergie lub szczególne potrzeby <span className="font-normal text-muted">(opcjonalnie)</span>
            <textarea
              rows="2"
              value={form.sensitive_data}
              onChange={(event) => onChange('sensitive_data', event.target.value)}
              className="field mt-2 min-h-20 resize-y"
              placeholder="Podaj tylko informacje potrzebne lokalowi do obsługi wizyty"
            />
          </label>
          {sensitiveProvided ? (
            <div className="mt-3">
              <label className="flex min-h-11 cursor-pointer items-start gap-3 text-sm leading-relaxed text-ink">
                <input
                  type="checkbox"
                  checked={form.sensitive_data_consent}
                  onChange={(event) => onChange('sensitive_data_consent', event.target.checked)}
                  className="mt-1 h-5 w-5 shrink-0 accent-mint"
                  aria-invalid={Boolean(errors.sensitive_data_consent)}
                  aria-describedby={describedBy(errors.sensitive_data_consent, 'public-reservation-sensitive-error')}
                />
                <span>{config.sensitive.label}</span>
              </label>
              {errors.sensitive_data_consent ? <p id="public-reservation-sensitive-error" className="mt-1 text-sm text-danger">{errors.sensitive_data_consent}</p> : null}
            </div>
          ) : null}
        </div>

        <div className="border-t border-line pt-5">
          <label className="flex min-h-11 cursor-pointer items-start gap-3 text-sm leading-relaxed text-ink">
            <input
              type="checkbox"
              checked={form.privacy_acknowledged}
              onChange={(event) => onChange('privacy_acknowledged', event.target.checked)}
              className="mt-1 h-5 w-5 shrink-0 accent-mint"
              required
              aria-invalid={Boolean(errors.privacy_acknowledged)}
              aria-describedby={describedBy(errors.privacy_acknowledged, 'public-reservation-privacy-error')}
            />
            <span>{config.privacy.notice_label}</span>
          </label>
          <a
            href="/?polityka"
            target="_blank"
            rel="noreferrer"
            className="ml-8 inline-flex min-h-11 items-center text-sm font-semibold text-mint underline decoration-mint/40 underline-offset-4 hover:decoration-mint"
          >
            Przeczytaj informację o prywatności
          </a>
          {config.privacy.notice_text ? (
            <details className="mt-2 rounded-xl border border-line bg-white/[0.025] px-4 py-3 text-sm text-muted">
              <summary className="min-h-11 cursor-pointer py-2 font-semibold text-ink">Najważniejsze informacje</summary>
              <p className="pb-2 leading-relaxed">{config.privacy.notice_text}</p>
            </details>
          ) : null}
          {errors.privacy_acknowledged ? <p id="public-reservation-privacy-error" className="mt-1 text-sm text-danger">{errors.privacy_acknowledged}</p> : null}

          <label className="mt-3 flex min-h-11 cursor-pointer items-start gap-3 text-sm leading-relaxed text-ink">
            <input
              type="checkbox"
              checked={form.marketing_consent}
              onChange={(event) => onChange('marketing_consent', event.target.checked)}
              className="mt-1 h-5 w-5 shrink-0 accent-mint"
            />
            <span>{config.marketing.label} <span className="text-muted">(opcjonalnie)</span></span>
          </label>
        </div>

        {submitError ? (
          <div className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3" role="alert">
            <p className="text-sm text-danger">{submitError}</p>
          </div>
        ) : null}

        <button
          type="submit"
          disabled={busy || holdExpired}
          className="min-h-12 w-full rounded-xl bg-cream px-4 py-3 text-sm font-semibold text-bg shadow-cta transition ease-snap hover:bg-white active:scale-[0.98] disabled:cursor-wait disabled:opacity-50"
        >
          {busy
            ? (isWaitlist ? 'Dodaję do listy…' : 'Rezerwuję…')
            : (isWaitlist ? 'Dołącz do listy' : 'Potwierdź rezerwację')}
        </button>
      </form>
    </section>
  )
}
