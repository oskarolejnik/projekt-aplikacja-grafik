import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { localDateIso, shiftDateIso, startOfWeekIso } from '../../lib/reservationRoute'
import { Icon } from '../../lib/icons'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'

const STATUS = {
  rezerwacja: { label: 'Nowa', className: 'bg-lemon/15 text-lemon' },
  potwierdzona: { label: 'Potwierdzona', className: 'bg-mint/15 text-mint' },
  odbyla: { label: 'Odbyła się', className: 'bg-white/[0.07] text-muted' },
  no_show: { label: 'No-show', className: 'bg-danger/15 text-danger' },
  odwolana: { label: 'Odwołana', className: 'bg-danger/10 text-muted' },
}

const dateLabel = (value, options) => {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day, 12).toLocaleDateString('pl-PL', options)
}

function CalendarSkeleton() {
  return (
    <div className="grid gap-2 md:grid-cols-7" role="status" aria-label="Ładowanie kalendarza rezerwacji">
      {[0, 1, 2, 3, 4, 5, 6].map((item) => (
        <div key={item} className="min-h-44 animate-pulse rounded-xl border border-line bg-white/[0.025] p-3 motion-reduce:animate-none">
          <div className="h-4 w-16 rounded bg-white/[0.07]" />
          <div className="mt-5 h-14 rounded-lg bg-white/[0.05]" />
        </div>
      ))}
      <span className="sr-only">Ładowanie kalendarza…</span>
    </div>
  )
}

export default function ReservationsCalendar({
  date,
  mode = 'week',
  status = '',
  active = true,
  canOpenDetails = true,
  onContextChange,
  onOpenDay,
  onOpenReservation,
}) {
  const [rows, setRows] = useState([])
  const [snapshotKey, setSnapshotKey] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [retry, setRetry] = useState(0)
  const requestId = useRef(0)
  const hasLoaded = useRef(false)

  const start = mode === 'day' ? date : startOfWeekIso(date)
  const end = mode === 'day' ? date : shiftDateIso(start, 6)
  const contextKey = `${start}:${end}:${status || '*'}`
  const hasCurrentSnapshot = snapshotKey === contextKey
  const visibleRows = hasCurrentSnapshot ? rows : []
  const days = useMemo(() => {
    const count = mode === 'day' ? 1 : 7
    return Array.from({ length: count }, (_, index) => shiftDateIso(start, index))
  }, [mode, start])

  useEffect(() => {
    if (!active) return undefined
    const id = ++requestId.current
    const controller = new AbortController()
    if (hasLoaded.current) setRefreshing(true)
    setError(null)
    const filter = status ? `&status=${encodeURIComponent(status)}` : ''
    api(`/rezerwacje-stolik?start=${start}&end=${end}${filter}`, 'GET', null, { signal: controller.signal })
      .then((response) => {
        if (id !== requestId.current) return
        setRows(response.rezerwacje || [])
        setSnapshotKey(contextKey)
        hasLoaded.current = true
      })
      .catch((reason) => {
        if (id !== requestId.current || reason?.name === 'AbortError') return
        setError(reason.message || 'Nie udało się wczytać kalendarza rezerwacji.')
      })
      .finally(() => {
        if (id !== requestId.current) return
        setRefreshing(false)
      })
    return () => {
      controller.abort()
      requestId.current += 1
    }
  }, [active, contextKey, end, retry, start, status])

  const grouped = useMemo(() => Object.fromEntries(days.map((day) => [
    day,
    visibleRows.filter((reservation) => reservation.data === day),
  ])), [days, visibleRows])

  const move = (direction) => {
    onContextChange?.({ date: shiftDateIso(date, direction * (mode === 'day' ? 1 : 7)) })
  }

  const renderReservation = (reservation) => {
    const meta = STATUS[reservation.status] || STATUS.rezerwacja
    return (
      <button
        key={reservation.id}
        type="button"
        onClick={() => onOpenReservation?.(reservation)}
        className="group w-full rounded-lg border border-white/[0.07] bg-white/[0.035] px-3 py-2.5 text-left transition hover:border-white/[0.14] hover:bg-white/[0.06] active:scale-[0.99]"
        aria-label={canOpenDetails
          ? `Otwórz rezerwację ${reservation.godz_od || 'bez godziny'}, ${reservation.nazwisko}`
          : `Otwórz dzień ${reservation.data}, ${reservation.godz_od || 'bez godziny'}`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-display text-sm font-semibold tabular-nums text-ink">
            {reservation.godz_od || '—'}
          </span>
          <span className={`rounded-full px-2 py-0.5 text-[0.65rem] font-semibold ${meta.className}`}>
            {meta.label}
          </span>
        </div>
        <p className="mt-1 truncate text-xs font-medium text-ink/90">{reservation.nazwisko}</p>
        <p className="mt-0.5 text-[0.7rem] text-muted">
          {reservation.liczba_osob ? `${reservation.liczba_osob} os.` : 'Liczba osób nieustalona'}
        </p>
      </button>
    )
  }

  return (
    <Card className="p-5 sm:p-8">
      <SectionHeader
        title="Kalendarz rezerwacji"
        subtitle="Tygodniowy obraz zajętości. Puste miejsce nie jest jeszcze potwierdzeniem dostępności — ostatecznie sprawdza ją silnik przy zapisie."
      >
        <span className="inline-flex min-h-5 items-center gap-1.5 text-xs text-muted" role="status" aria-live="polite">
          {refreshing ? <><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Aktualizuję…</> : null}
        </span>
      </SectionHeader>

      <div className="mb-5 flex flex-wrap items-center gap-2 border-b border-line pb-5">
        <Button variant="subtle" size="sm" onClick={() => move(-1)} aria-label={mode === 'day' ? 'Poprzedni dzień' : 'Poprzedni tydzień'}>
          <span aria-hidden className="text-lg leading-none">‹</span>
        </Button>
        <Button variant="subtle" size="sm" onClick={() => move(1)} aria-label={mode === 'day' ? 'Następny dzień' : 'Następny tydzień'}>
          <span aria-hidden className="text-lg leading-none">›</span>
        </Button>
        <Button variant="ghost" size="sm" onClick={() => onContextChange?.({ date: localDateIso() })} disabled={date === localDateIso()}>Dzisiaj</Button>
        <p className="min-w-0 flex-1 text-sm font-semibold capitalize text-ink">
          {mode === 'day'
            ? dateLabel(date, { weekday: 'long', day: 'numeric', month: 'long' })
            : `${dateLabel(start, { day: 'numeric', month: 'short' })} – ${dateLabel(end, { day: 'numeric', month: 'short', year: 'numeric' })}`}
        </p>
        <div className="inline-flex rounded-xl border border-line bg-white/[0.025] p-1" aria-label="Zakres kalendarza">
          {[
            ['day', 'Dzień'],
            ['week', 'Tydzień'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => onContextChange?.({ mode: value })}
              aria-pressed={mode === value}
              className={`min-h-11 rounded-lg px-3 text-xs font-semibold transition ${mode === value ? 'bg-white/[0.10] text-ink' : 'text-muted hover:text-ink'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="sr-only" htmlFor="reservation-calendar-status">Status rezerwacji</label>
        <select
          id="reservation-calendar-status"
          className="field w-auto min-w-[10rem]"
          value={status}
          onChange={(event) => onContextChange?.({ status: event.target.value })}
        >
          <option value="">Wszystkie statusy</option>
          <option value="rezerwacja">Nowe</option>
          <option value="potwierdzona">Potwierdzone</option>
          <option value="odbyla">Odbyte</option>
          <option value="no_show">No-show</option>
          <option value="odwolana">Odwołane</option>
        </select>
      </div>

      {error ? (
        <div role="alert">
          <Banner variant="danger" className="mb-4">
            <div className="flex flex-wrap items-center gap-3">
              <span>{error}</span>
              <Button variant="ghost" size="sm" onClick={() => setRetry((value) => value + 1)}>Ponów</Button>
            </div>
          </Banner>
        </div>
      ) : null}

      {error && !hasCurrentSnapshot ? null : !hasCurrentSnapshot ? <CalendarSkeleton /> : (
        <>
          {mode === 'week' ? (
            <div className="mb-4 grid grid-cols-7 gap-1 md:hidden" aria-label="Dni tygodnia">
              {days.map((day) => (
                <button
                  key={day}
                  type="button"
                  onClick={() => onContextChange?.({ date: day })}
                  aria-current={day === date ? 'date' : undefined}
                  aria-label={dateLabel(day, { weekday: 'long', day: 'numeric', month: 'long' })}
                  className={`min-h-11 min-w-0 rounded-xl px-1 py-1.5 text-center transition ${day === date ? 'bg-mint text-bg' : 'border border-line bg-white/[0.03] text-muted'}`}
                >
                  <span aria-hidden className="block text-[0.58rem] font-semibold uppercase">{dateLabel(day, { weekday: 'short' }).replace('.', '').slice(0, 2)}</span>
                  <span className="block text-sm font-bold">{dateLabel(day, { day: 'numeric' })}</span>
                </button>
              ))}
            </div>
          ) : null}

          <div className={mode === 'week' ? 'md:grid md:grid-cols-7 md:gap-2' : ''}>
            {days.map((day) => {
              const dayRows = grouped[day] || []
              const guests = dayRows.reduce((sum, item) => sum + (Number(item.liczba_osob) || 0), 0)
              const mobileHidden = mode === 'week' && day !== date ? 'hidden md:block' : ''
              return (
                <section key={day} className={`min-h-52 rounded-xl border border-line bg-white/[0.02] p-3 ${mobileHidden}`} aria-label={dateLabel(day, { weekday: 'long', day: 'numeric', month: 'long' })}>
                  <div className="mb-3 flex items-start justify-between gap-2 border-b border-line pb-3">
                    <div>
                      <p className="text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-muted">{dateLabel(day, { weekday: 'short' }).replace('.', '')}</p>
                      <p className="mt-0.5 font-display text-sm font-semibold text-ink">{dateLabel(day, { day: 'numeric', month: 'short' })}</p>
                    </div>
                    <span className="text-right text-[0.65rem] leading-relaxed text-muted">{dayRows.length} rez.<br />{guests} os.</span>
                  </div>
                  <div className="space-y-2">
                    {dayRows.length ? dayRows.map(renderReservation) : (
                      <p className="rounded-lg border border-dashed border-line px-2 py-5 text-center text-xs text-muted">Bez rezerwacji</p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => onOpenDay?.(day)}
                    className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg text-xs font-semibold text-muted transition hover:bg-white/[0.05] hover:text-ink"
                  >
                    <Icon name="calendar" className="h-4 w-4" />
                    Otwórz dzień
                  </button>
                </section>
              )
            })}
          </div>
        </>
      )}
    </Card>
  )
}
