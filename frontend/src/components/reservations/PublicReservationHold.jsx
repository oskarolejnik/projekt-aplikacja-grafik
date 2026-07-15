import { formatCountdown } from '../../lib/publicReservation'

export default function PublicReservationHold({ remainingSeconds }) {
  return (
    <div
      className="mt-5 flex min-h-12 items-center justify-between gap-4 rounded-xl border border-mint/30 bg-mint/[0.07] px-4 py-3"
      aria-label={`Wybrany termin jest zabezpieczony jeszcze przez ${formatCountdown(remainingSeconds)}`}
    >
      <span className="text-sm text-ink">Trzymamy ten termin dla Ciebie</span>
      <span className="shrink-0 text-sm font-semibold tabular-nums text-mint" data-testid="hold-countdown" aria-hidden="true">
        {formatCountdown(remainingSeconds)}
      </span>
    </div>
  )
}
