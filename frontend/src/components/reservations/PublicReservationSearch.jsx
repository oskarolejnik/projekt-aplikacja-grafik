import { formatReservationDate } from '../../lib/publicReservation'

export default function PublicReservationSearch({
  headingRef,
  date,
  people,
  minDate,
  status,
  slots,
  alternatives,
  error,
  alternativesError,
  slotError,
  selectingSlot,
  onDateChange,
  onPeopleChange,
  onSearch,
  onSelectSlot,
  onJoinWaitlist,
}) {
  const hasSlots = slots.length > 0
  const noAvailability = status === 'success' && !hasSlots

  return (
    <section aria-labelledby="public-reservation-search-title">
      <h2
        ref={headingRef}
        id="public-reservation-search-title"
        tabIndex="-1"
        className="font-display text-xl font-semibold tracking-tight text-ink outline-none"
      >
        Znajdź stolik
      </h2>
      <p className="mt-2 text-base leading-relaxed text-muted">
        Wybierz dzień i liczbę gości. Pokażemy tylko godziny, które można od razu zarezerwować.
      </p>

      <form className="mt-6" onSubmit={onSearch} noValidate>
        <div data-testid="reservation-search-fields" className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-ink">
            Data
            <input
              type="date"
              min={minDate}
              value={date}
              onChange={(event) => onDateChange(event.target.value)}
              disabled={selectingSlot}
              className="field mt-2 min-h-12 disabled:cursor-wait disabled:opacity-60"
              required
            />
          </label>
          <label className="block text-sm font-medium text-ink">
            Liczba osób
            <input
              type="number"
              min="1"
              inputMode="numeric"
              value={people}
              onChange={(event) => onPeopleChange(event.target.value)}
              disabled={selectingSlot}
              className="field mt-2 min-h-12 disabled:cursor-wait disabled:opacity-60"
              required
            />
          </label>
        </div>
        <button
          type="submit"
          disabled={status === 'loading' || selectingSlot}
          className="mt-5 min-h-12 w-full rounded-xl bg-cream px-4 py-3 text-sm font-semibold text-bg shadow-cta transition ease-snap hover:bg-white active:scale-[0.98] disabled:cursor-wait disabled:opacity-50"
        >
          {status === 'loading' ? 'Sprawdzam dostępność…' : 'Pokaż wolne godziny'}
        </button>
      </form>

      {status === 'loading' ? (
        <p className="mt-5 text-center text-sm text-muted" role="status">
          Szukam najlepszego terminu…
        </p>
      ) : null}

      {error ? (
        <div className="mt-5 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3" role="alert">
          <p className="text-sm text-danger">{error}</p>
          <button
            type="button"
            onClick={onSearch}
            className="mt-3 min-h-11 rounded-xl border border-danger/30 px-4 text-sm font-semibold text-ink transition hover:bg-white/[0.05] active:scale-[0.98]"
          >
            Spróbuj ponownie
          </button>
        </div>
      ) : null}

      {hasSlots ? (
        <div className="mt-7" aria-labelledby="public-reservation-times-title">
          <h3 id="public-reservation-times-title" className="text-sm font-semibold text-ink">
            Dostępne godziny · <span className="capitalize">{formatReservationDate(date)}</span>
          </h3>
          <div className="mt-3 grid grid-cols-2 gap-2 min-[360px]:grid-cols-3 sm:grid-cols-4">
            {slots.map((slot) => (
              <button
                key={`${date}-${slot.godz_od}`}
                type="button"
                disabled={selectingSlot}
                onClick={() => onSelectSlot({ ...slot, data: date })}
                className="min-h-12 rounded-xl border border-line bg-white/[0.025] px-3 py-2 text-sm font-semibold text-ink transition ease-snap hover:border-mint/60 hover:bg-mint/[0.08] active:scale-[0.98] disabled:cursor-wait disabled:opacity-50"
                aria-label={`Wybierz godzinę ${slot.godz_od}`}
              >
                {slot.godz_od}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {slotError ? (
        <div className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3" role="alert">
          <p className="text-sm text-danger">{slotError}</p>
          <button
            type="button"
            onClick={onSearch}
            className="mt-3 min-h-11 rounded-xl border border-danger/30 px-4 text-sm font-semibold text-ink transition hover:bg-white/[0.05] active:scale-[0.98]"
          >
            Odśwież godziny
          </button>
        </div>
      ) : null}

      {selectingSlot ? (
        <p className="mt-4 text-center text-sm text-muted" role="status">
          Zabezpieczam wybraną godzinę…
        </p>
      ) : null}

      {noAvailability ? (
        <div className="mt-7" aria-labelledby="public-reservation-alternatives-title">
          <h3 id="public-reservation-alternatives-title" className="text-base font-semibold text-ink">
            Ten dzień jest już pełny
          </h3>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            Sprawdź najbliższe dostępne terminy albo dołącz do listy oczekujących.
          </p>

          {alternativesError ? (
            <div className="mt-4 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3" role="alert">
              <p className="text-sm text-danger">{alternativesError}</p>
              <button
                type="button"
                onClick={onSearch}
                className="mt-3 min-h-11 rounded-xl border border-danger/30 px-4 text-sm font-semibold text-ink transition hover:bg-white/[0.05] active:scale-[0.98]"
              >
                Sprawdź ponownie
              </button>
            </div>
          ) : alternatives.length > 0 ? (
            <div className="mt-4 space-y-2">
              {alternatives.map((alternative) => (
                <button
                  key={`${alternative.data}-${alternative.godz_od}`}
                  type="button"
                  disabled={selectingSlot}
                  onClick={() => onSelectSlot(alternative)}
                  className="flex min-h-12 w-full items-center justify-between gap-4 rounded-xl border border-line bg-white/[0.025] px-4 py-3 text-left transition ease-snap hover:border-mint/60 hover:bg-mint/[0.08] active:scale-[0.99] disabled:cursor-wait disabled:opacity-50"
                >
                  <span className="min-w-0 text-sm font-medium text-ink capitalize">
                    {formatReservationDate(alternative.data)}
                  </span>
                  <span className="shrink-0 text-sm font-semibold text-mint">
                    {alternative.godz_od}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-muted">Nie znaleźliśmy wolnego terminu w najbliższych dniach.</p>
          )}

          <div className="mt-5 border-t border-line pt-5">
            <button
              type="button"
              onClick={onJoinWaitlist}
              disabled={selectingSlot}
              className="min-h-12 w-full rounded-xl border border-line bg-white/[0.025] px-4 py-3 text-sm font-semibold text-ink transition ease-snap hover:bg-white/[0.06] active:scale-[0.98] disabled:cursor-wait disabled:opacity-50"
            >
              Dołącz do listy oczekujących
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
