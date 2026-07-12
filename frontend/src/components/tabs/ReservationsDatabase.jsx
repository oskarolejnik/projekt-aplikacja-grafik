import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'

const PAGE_SIZE = 25

const STATUS_LABELS = {
  rezerwacja: 'Nowa',
  potwierdzona: 'Potwierdzona',
  odbyla: 'Odbyła się',
  no_show: 'No-show',
  odwolana: 'Odwołana',
}

function DatabaseSkeleton() {
  return (
    <div className="space-y-2" role="status" aria-label="Ładowanie bazy rezerwacji">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex min-h-[74px] animate-pulse items-center gap-4 rounded-xl border border-line bg-white/[0.025] px-4 py-3 motion-reduce:animate-none">
          <div className="h-4 w-24 rounded bg-white/[0.07]" />
          <div className="flex-1 space-y-2"><div className="h-4 w-40 rounded bg-white/[0.07]" /><div className="h-3 w-28 rounded bg-white/[0.05]" /></div>
          <div className="h-7 w-24 rounded-full bg-white/[0.05]" />
        </div>
      ))}
      <span className="sr-only">Ładowanie bazy…</span>
    </div>
  )
}

export default function ReservationsDatabase({ route, active = true, onContextChange, onOpenReservation }) {
  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [snapshotKey, setSnapshotKey] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [validation, setValidation] = useState(null)
  const [searchVersion, setSearchVersion] = useState(0)
  const requestId = useRef(0)
  const hasLoaded = useRef(false)
  const contextKey = JSON.stringify([
    route.from,
    route.to,
    route.status || '',
    route.sort,
    route.offset,
    submittedQuery,
  ])
  const hasCurrentSnapshot = snapshotKey === contextKey
  const visibleRows = hasCurrentSnapshot ? rows : []
  const visibleTotal = hasCurrentSnapshot ? total : 0

  useEffect(() => {
    if (!active) return undefined
    const id = ++requestId.current
    const controller = new AbortController()
    if (hasLoaded.current) setRefreshing(true)
    setError(null)
    api('/rezerwacje-stolik/wyszukaj', 'POST', {
      start: route.from,
      end: route.to,
      query: submittedQuery || null,
      status: route.status || null,
      sort: route.sort,
      offset: route.offset,
      limit: PAGE_SIZE,
    }, { signal: controller.signal })
      .then((response) => {
        if (id !== requestId.current) return
        setRows(response.rezerwacje || [])
        setTotal(response.total || 0)
        setSnapshotKey(contextKey)
        hasLoaded.current = true
      })
      .catch((reason) => {
        if (id !== requestId.current || reason?.name === 'AbortError') return
        setError(reason.message || 'Nie udało się przeszukać bazy rezerwacji.')
      })
      .finally(() => {
        if (id !== requestId.current) return
        setRefreshing(false)
      })
    return () => {
      controller.abort()
      requestId.current += 1
    }
  }, [active, contextKey, route.from, route.offset, route.sort, route.status, route.to, searchVersion, submittedQuery])

  const submit = (event) => {
    event?.preventDefault()
    const normalized = query.trim()
    if (normalized && normalized.length < 2) {
      setValidation('Wpisz co najmniej 2 znaki nazwiska lub telefonu.')
      return
    }
    setValidation(null)
    setSubmittedQuery(normalized)
    if (route.offset) onContextChange?.({ offset: 0 }, { replace: true })
    else setSearchVersion((value) => value + 1)
  }

  const pageStart = visibleTotal ? route.offset + 1 : 0
  const pageEnd = Math.min(route.offset + visibleRows.length, visibleTotal)

  return (
    <Card className="p-5 sm:p-8">
      <SectionHeader
        title="Baza rezerwacji"
        subtitle="Wyszukiwanie po nazwisku lub telefonie odbywa się bez zapisywania tej frazy w adresie i historii przeglądarki."
      >
        <span className="inline-flex min-h-5 items-center gap-1.5 text-xs text-muted" role="status" aria-live="polite">
          {refreshing ? <><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Aktualizuję…</> : null}
        </span>
      </SectionHeader>

      <form onSubmit={submit} className="mb-5 space-y-4 border-b border-line pb-5" role="search">
        <div className="grid gap-3 lg:grid-cols-[minmax(15rem,1fr)_auto_auto_auto]">
          <div>
            <label className="field-label" htmlFor="reservation-database-query">Nazwisko lub telefon</label>
            <div className="relative mt-1.5">
              <Icon name="users" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                id="reservation-database-query"
                className="field pl-10"
                value={query}
                onChange={(event) => { setQuery(event.target.value); setValidation(null) }}
                placeholder="np. Kowalska lub 600 123 456"
                autoComplete="off"
                spellCheck="false"
              />
            </div>
          </div>
          <div>
            <label className="field-label" htmlFor="reservation-database-from">Od</label>
            <input id="reservation-database-from" type="date" className="field mt-1.5 w-auto" value={route.from} onChange={(event) => onContextChange?.({ from: event.target.value, offset: 0 }, { replace: true })} />
          </div>
          <div>
            <label className="field-label" htmlFor="reservation-database-to">Do</label>
            <input id="reservation-database-to" type="date" className="field mt-1.5 w-auto" value={route.to} onChange={(event) => onContextChange?.({ to: event.target.value, offset: 0 }, { replace: true })} />
          </div>
          <div className="flex items-end">
            <Button type="submit" className="w-full lg:w-auto">
              <Icon name="search" className="h-4 w-4" />
              Szukaj
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <div>
            <label className="sr-only" htmlFor="reservation-database-status">Status</label>
            <select id="reservation-database-status" className="field w-auto min-w-[11rem]" value={route.status} onChange={(event) => onContextChange?.({ status: event.target.value, offset: 0 }, { replace: true })}>
              <option value="">Wszystkie statusy</option>
              <option value="rezerwacja">Nowe</option>
              <option value="potwierdzona">Potwierdzone</option>
              <option value="odbyla">Odbyte</option>
              <option value="no_show">No-show</option>
              <option value="odwolana">Odwołane</option>
            </select>
          </div>
          <div>
            <label className="sr-only" htmlFor="reservation-database-sort">Sortowanie</label>
            <select id="reservation-database-sort" className="field w-auto min-w-[12rem]" value={route.sort} onChange={(event) => onContextChange?.({ sort: event.target.value, offset: 0 }, { replace: true })}>
              <option value="data_desc">Najnowsze najpierw</option>
              <option value="data_asc">Najstarsze najpierw</option>
              <option value="nazwisko_asc">Nazwisko A–Z</option>
            </select>
          </div>
          {submittedQuery ? (
            <Button
              variant="subtle"
              size="sm"
              onClick={() => { setQuery(''); setSubmittedQuery(''); setSearchVersion((value) => value + 1) }}
            >
              <Icon name="close" className="h-4 w-4" /> Wyczyść wyszukiwanie
            </Button>
          ) : null}
        </div>
        <p className={`min-h-5 text-xs ${validation ? 'text-danger' : 'text-muted'}`} role={validation ? 'alert' : 'status'} aria-live="polite">
          {validation || (submittedQuery ? `Wyniki dla: „${submittedQuery}”` : 'Pusta fraza pokazuje rezerwacje z wybranego zakresu.')}
        </p>
      </form>

      {error ? (
        <div role="alert">
          <Banner variant="danger" className="mb-4">
            <div className="flex flex-wrap items-center gap-3">
              <span>{error}</span>
              <Button variant="ghost" size="sm" onClick={() => setSearchVersion((value) => value + 1)}>Ponów</Button>
            </div>
          </Banner>
        </div>
      ) : null}

      {error && !hasCurrentSnapshot ? null : !hasCurrentSnapshot ? <DatabaseSkeleton /> : visibleRows.length === 0 && !error ? (
        <div className="rounded-xl border border-dashed border-line px-5 py-12 text-center">
          <p className="text-sm font-semibold text-ink">Brak pasujących rezerwacji</p>
          <p className="mt-1 text-sm text-muted">Zmień zakres, status albo sprawdź wpisaną frazę.</p>
        </div>
      ) : (
        <div className="space-y-2" aria-busy={refreshing || undefined}>
          {visibleRows.map((reservation) => (
            <button
              key={reservation.id}
              type="button"
              onClick={() => onOpenReservation?.(reservation)}
              className="flex min-h-[76px] w-full flex-col gap-2 rounded-xl border border-line bg-white/[0.025] px-4 py-3 text-left transition hover:border-white/[0.14] hover:bg-white/[0.05] active:scale-[0.995] sm:flex-row sm:items-center sm:gap-4"
              aria-label={`Otwórz rezerwację: ${reservation.nazwisko}, ${reservation.data}`}
            >
              <div className="w-28 shrink-0">
                <p className="font-display text-sm font-semibold tabular-nums text-ink">{reservation.data}</p>
                <p className="mt-0.5 text-xs tabular-nums text-muted">{reservation.godz_od || 'Bez godziny'}</p>
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">{reservation.nazwisko}</p>
                <p className="mt-0.5 truncate text-xs text-muted">
                  {reservation.telefon || 'Brak telefonu'}{reservation.liczba_osob ? ` · ${reservation.liczba_osob} os.` : ''}
                </p>
              </div>
              <span className="text-xs font-semibold text-muted">{STATUS_LABELS[reservation.status] || reservation.status}</span>
              <Icon name="chevronDown" className="hidden h-4 w-4 -rotate-90 text-muted sm:block" />
            </button>
          ))}
        </div>
      )}

      {hasCurrentSnapshot && !error && visibleTotal > 0 ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
          <p className="text-xs text-muted">{pageStart}–{pageEnd} z {visibleTotal}</p>
          <div className="flex gap-2">
            <Button variant="subtle" size="sm" disabled={route.offset === 0} onClick={() => onContextChange?.({ offset: Math.max(0, route.offset - PAGE_SIZE) })}>Poprzednia</Button>
            <Button variant="subtle" size="sm" disabled={route.offset + PAGE_SIZE >= visibleTotal} onClick={() => onContextChange?.({ offset: route.offset + PAGE_SIZE })}>Następna</Button>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
