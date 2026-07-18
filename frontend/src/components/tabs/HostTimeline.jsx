const parseMinutes = (value) => {
  const [hours, minutes] = String(value || '').split(':').map(Number)
  return Number.isFinite(hours) && Number.isFinite(minutes) ? hours * 60 + minutes : null
}

const absoluteMinutes = (value, origin) => {
  const parsed = parseMinutes(value)
  if (parsed == null) return null
  return parsed < origin ? parsed + 1440 : parsed
}

const statusClass = (phase) => {
  if (phase === 'rachunek') return 'border-lemon/45 bg-lemon/18 text-ink'
  if (phase === 'oplacony') return 'border-white/[0.18] bg-white/[0.10] text-ink'
  if (phase === 'posadzony') return 'border-mint/45 bg-mint/18 text-ink'
  return 'border-info/35 bg-info/12 text-ink'
}

const timeLabel = (value) => String(value || '').slice(0, 5)

export default function HostTimeline({ timeline, canViewContacts = false }) {
  const tables = timeline?.stoly || []
  const reservations = timeline?.zajetosci || []
  const slots = (timeline?.godziny || []).map(parseMinutes).filter(Number.isFinite)
  const reservationTimes = reservations.flatMap((entry) => [parseMinutes(entry.godz_od), parseMinutes(entry.godz_do)]).filter(Number.isFinite)
  const origin = slots[0] ?? reservationTimes[0] ?? 12 * 60
  const absoluteSlots = slots.map((slot) => slot < origin ? slot + 1440 : slot)
  const absoluteReservationTimes = reservationTimes.map((slot) => slot < origin ? slot + 1440 : slot)
  const start = Math.min(origin, ...absoluteSlots, ...absoluteReservationTimes)
  const inferredStep = absoluteSlots.length > 1
    ? Math.max(15, absoluteSlots[1] - absoluteSlots[0])
    : 30
  const end = Math.max(start + 6 * 60, ...absoluteSlots.map((slot) => slot + inferredStep), ...absoluteReservationTimes)
  const duration = Math.max(60, end - start)
  const canvasWidth = Math.max(680, Math.round(duration * 1.25))
  const ticks = []
  for (let minute = Math.ceil(start / 60) * 60; minute <= end; minute += 60) ticks.push(minute)

  if (!timeline || tables.length === 0) {
    return (
      <section aria-labelledby="host-timeline-title">
        <TimelineHeading />
        <div className="mt-4 grid min-h-40 place-items-center rounded-2xl border border-dashed border-line px-6 text-center">
          <p className="text-sm text-muted">Brak stolików do pokazania na osi czasu.</p>
        </div>
      </section>
    )
  }

  return (
    <section aria-labelledby="host-timeline-title" className="min-w-0">
      <TimelineHeading />
      <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-white/[0.018]" tabIndex={0} aria-label="Przewijana oś czasu stolików">
        <div style={{ width: `${canvasWidth + 112}px` }} className="min-w-full">
          <div className="sticky top-0 z-20 flex h-10 border-b border-line bg-bg-2/95 text-[0.68rem] font-semibold text-muted backdrop-blur-xl">
            <div className="sticky left-0 z-30 grid w-28 shrink-0 place-items-center border-r border-line bg-bg-2/95 px-3 text-left">Stolik</div>
            <div className="relative flex-1" aria-hidden>
              {ticks.map((minute) => (
                <span
                  key={minute}
                  className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 tabular-nums"
                  style={{ left: `${((minute - start) / duration) * 100}%` }}
                >
                  {String(Math.floor((minute % 1440) / 60)).padStart(2, '0')}:00
                </span>
              ))}
            </div>
          </div>

          {tables.map((table) => {
            const entries = reservations.filter((entry) => entry.stolik_id === table.id)
            return (
              <div key={table.id} className="group flex min-h-14 border-b border-line/70 last:border-b-0">
                <div className="sticky left-0 z-10 flex w-28 shrink-0 items-center border-r border-line bg-bg-2/95 px-3 backdrop-blur-xl">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-ink" title={table.nazwa}>{table.nazwa}</p>
                    <p className="mt-0.5 truncate text-[0.65rem] text-muted">{table.sekcja || table.strefa || 'Sala'}</p>
                  </div>
                </div>
                <div className="relative flex-1 bg-surface/25 group-hover:bg-white/[0.025]">
                  {ticks.map((minute) => (
                    <span
                      key={minute}
                      aria-hidden
                      className="absolute inset-y-0 border-l border-white/[0.045]"
                      style={{ left: `${((minute - start) / duration) * 100}%` }}
                    />
                  ))}
                  {entries.map((entry, index) => {
                    const entryStart = absoluteMinutes(entry.godz_od, origin)
                    let entryEnd = absoluteMinutes(entry.godz_do, origin)
                    if (entryStart == null || entryEnd == null) return null
                    if (entryEnd <= entryStart) entryEnd += 1440
                    const left = Math.max(0, ((entryStart - start) / duration) * 100)
                    const width = Math.max(1.5, (Math.min(entryEnd, end) - Math.max(entryStart, start)) / duration * 100)
                    const guest = canViewContacts ? entry.nazwisko || 'Gość' : 'Gość'
                    const label = `${guest} · ${timeLabel(entry.godz_od)}–${timeLabel(entry.godz_do)}`
                    return (
                      <div
                        key={`${entry.rezerwacja_id}:${index}`}
                        tabIndex={0}
                        className={`absolute inset-y-2 flex min-w-8 items-center overflow-hidden rounded-lg border px-2 text-[0.68rem] font-semibold shadow-soft outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-mint/70 ${statusClass(entry.faza_hosta)}`}
                        style={{ left: `${left}%`, width: `${width}%` }}
                        aria-label={`${table.nazwa}: ${label}${entry.liczba_osob ? `, ${entry.liczba_osob} osób` : ''}`}
                        title={label}
                      >
                        <span className="truncate">{guest}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-muted">Przewiń poziomo, aby zobaczyć późniejsze godziny. Łączona rezerwacja zajmuje osobny pasek na każdym użytym stoliku.</p>
    </section>
  )
}

function TimelineHeading() {
  return (
    <div>
      <h3 id="host-timeline-title" className="text-base font-semibold text-ink">Oś czasu</h3>
      <p className="mt-0.5 text-xs text-muted">Jedna kolejność wizyt dla wszystkich stolików</p>
    </div>
  )
}
