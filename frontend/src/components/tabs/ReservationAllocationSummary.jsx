import { useId, useState } from 'react'
import { Button } from '../ui/Button'

const REASON_LABELS = {
  CAPACITY_FIT: 'Liczba miejsc jest dobrze dopasowana do grupy',
  TABLES_ADJACENT: 'Stoły sąsiadują i można je wygodnie połączyć',
  ROOM_STRICT_PRIORITY: 'Wybrana sala jest obsadzana jako pierwsza',
  ROOM_PREFERRED: 'Wybrano preferowaną salę',
  FEWER_JOINED_TABLES: 'Wybrano możliwie prosty układ stołów',
  MANUAL_LOCK: 'Przydział został wybrany przez obsługę',
}

const roomName = (allocation) => allocation?.room?.name || allocation?.room?.nazwa || null

const tableName = (table) => table?.name || table?.nazwa || null

const tableNames = (allocation) => {
  const names = (allocation?.tables || []).map(tableName).filter(Boolean)
  if (names.length) return names.join(' + ')
  return allocation?.label || null
}

const numericCapacity = (allocation) => {
  const value = typeof allocation?.capacity === 'object'
    ? allocation.capacity.seats ?? allocation.capacity.max
    : allocation?.capacity
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

const reasonText = (reason) => reason?.message || REASON_LABELS[reason?.code] || null

const alternativeCountLabel = (count) => {
  if (count === 1) return '1 alternatywę'
  const lastTwo = count % 100
  const last = count % 10
  return `${count} ${last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 'alternatywy' : 'alternatyw'}`
}

const alternativeTitle = (alternative, exact) => {
  if (alternative?.kind === 'waitlist') return 'Lista oczekujących'
  if (alternative?.kind === 'approval') return 'Do zatwierdzenia przez obsługę'

  const time = alternative?.time || alternative?.godz_od || null
  const date = alternative?.date || alternative?.data || null
  const when = [date, time].filter(Boolean).join(' · ')
  if (!exact) {
    if (alternative?.kind === 'room') return when || 'Inne dostępne miejsce'
    return when || 'Inny dostępny termin'
  }

  const suggested = alternative?.allocation || alternative
  const place = [roomName(suggested), tableNames(suggested)].filter(Boolean).join(' · ')
  return [when, place].filter(Boolean).join(' · ') || 'Inny dostępny wariant'
}

const stateHeading = (state, exact) => {
  if (!exact) return state === 'assigned' || state === 'manual_locked' ? 'Miejsce przydzielone' : 'Miejsce jest dostępne'
  if (state === 'assigned') return 'Przydzielono'
  if (state === 'manual_locked') return 'Przypisano ręcznie'
  return 'Proponowany przydział'
}

export default function ReservationAllocationSummary({
  allocation,
  alternatives: alternativesProp,
  onSelectAlternative,
  disabled = false,
  className = '',
}) {
  const headingId = useId()
  const alternativesId = useId()
  const [alternativesOpen, setAlternativesOpen] = useState(false)

  if (!allocation) return null

  const state = allocation.state || 'preview'
  const exact = allocation.visibility !== 'availability_only'
  const alternatives = Array.isArray(alternativesProp)
    ? alternativesProp
    : Array.isArray(allocation.alternatives) ? allocation.alternatives : []
  const reasons = exact ? (allocation.reasons || []).map(reasonText).filter(Boolean) : []
  const room = exact ? roomName(allocation) : null
  const tables = exact ? tableNames(allocation) : null
  const capacity = exact ? numericCapacity(allocation) : null
  const visitEnd = allocation.visit_end || allocation.godz_do || null
  const heading = stateHeading(state, exact)
  const primaryLine = exact
    ? [room, tables].filter(Boolean).join(' · ') || 'Stolik zostanie dobrany przy zapisie'
    : 'Dokładny stolik przydzieli obsługa'
  const detailLine = exact
    ? [capacity ? `${capacity} miejsc` : null, visitEnd ? `do ${visitEnd}` : null].filter(Boolean).join(' · ')
    : 'Szczegóły przydziału nie są udostępniane w tym widoku.'

  return (
    <section className={`min-w-0 border-y border-line ${className}`} aria-labelledby={headingId}>
      <div className="min-w-0 py-4">
        <h4 id={headingId} className="text-sm font-semibold text-ink">{heading}</h4>
        <div className="mt-1 min-w-0" aria-live="polite" aria-atomic="true">
          <p className="min-w-0 break-words text-base font-semibold leading-snug text-ink">{primaryLine}</p>
          {detailLine ? <p className="mt-1 break-words text-sm leading-relaxed text-muted">{detailLine}</p> : null}
          {state === 'manual_locked' ? (
            <p className="mt-1 break-words text-xs leading-relaxed text-muted">Automat nie zmieni tego przydziału.</p>
          ) : null}
        </div>
      </div>

      {reasons.length ? (
        <ul className="divide-y divide-line border-t border-line" aria-label="Powody wyboru przydziału">
          {reasons.map((reason, index) => (
            <li key={`${reason}-${index}`} className="flex min-w-0 items-start gap-2.5 py-3 text-sm text-muted">
              <span aria-hidden="true" className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-mint" />
              <span className="min-w-0 break-words leading-relaxed">{reason}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {alternatives.length ? (
        <div className="border-t border-line py-2">
          <Button
            variant="subtle"
            size="sm"
            className="w-full justify-start px-3 text-left sm:w-auto"
            aria-expanded={alternativesOpen}
            aria-controls={alternativesId}
            onClick={() => setAlternativesOpen((current) => !current)}
          >
            {alternativesOpen ? 'Ukryj alternatywy' : `Pokaż ${alternativeCountLabel(alternatives.length)}`}
            <span aria-hidden="true" className={`text-base leading-none transition-transform duration-150 motion-reduce:transition-none ${alternativesOpen ? 'rotate-180' : ''}`}>⌄</span>
          </Button>
        </div>
      ) : null}

      {alternatives.length && alternativesOpen ? (
        <ul id={alternativesId} className="divide-y divide-line border-t border-line" aria-label="Alternatywne przydziały">
          {alternatives.map((alternative, index) => {
            const label = alternativeTitle(alternative, exact)
            return (
              <li key={alternative?.id || alternative?.key || `${alternative?.kind || 'alternative'}-${index}`} className="min-w-0 py-1">
                {onSelectAlternative ? (
                  <button
                    type="button"
                    className="flex min-h-11 w-full min-w-0 items-center rounded-lg px-3 py-2 text-left text-sm font-medium text-ink transition duration-150 ease-snap hover:bg-white/[0.05] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint/60 disabled:pointer-events-none disabled:opacity-50"
                    onClick={() => onSelectAlternative(alternative, index)}
                    disabled={disabled}
                  >
                    <span className="min-w-0 break-words">{label}</span>
                  </button>
                ) : (
                  <span className="flex min-h-11 min-w-0 items-center px-3 py-2 text-sm text-muted">
                    <span className="min-w-0 break-words">{label}</span>
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      ) : null}

      {state === 'preview' ? (
        <p className="border-t border-line py-3 text-xs leading-relaxed text-muted">
          Podgląd nie blokuje stołów; przydział potwierdzi się przy zapisie.
        </p>
      ) : null}
    </section>
  )
}
