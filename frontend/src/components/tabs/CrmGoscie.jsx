import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import GuestProfileDialog from './GuestProfileDialog'

const PAGE_SIZE = 25
const SEARCH_DELAY_MS = 350

const RYZYKO = {
  wysokie: 'bg-danger/15 text-danger',
  srednie: 'bg-lemon/15 text-lemon',
  niskie: 'bg-white/[0.06] text-muted',
}

const DEFAULT_FILTERS = Object.freeze({
  vip: '',
  ryzyko: '',
  minWizyt: '1',
  sort: 'ostatnia_data_desc',
})

const normalizeResponse = (response, fallbackOffset) => {
  if (Array.isArray(response)) {
    return {
      goscie: response,
      total: response.length,
      offset: fallbackOffset,
      limit: PAGE_SIZE,
      podsumowanie: {},
    }
  }
  return {
    goscie: response?.goscie || [],
    total: Number(response?.total) || 0,
    offset: Number(response?.offset) || 0,
    limit: Number(response?.limit) || PAGE_SIZE,
    podsumowanie: response?.podsumowanie || {},
  }
}

const resultContext = ({ query, filters, offset }) => JSON.stringify({
  q: query,
  vip: filters.vip,
  ryzyko: filters.ryzyko,
  min_wizyt: filters.minWizyt,
  sort: filters.sort,
  offset,
})

export default function CrmGoscie() {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [offset, setOffset] = useState(0)
  const [result, setResult] = useState(null)
  const [snapshotKey, setSnapshotKey] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState(null)
  const [retryVersion, setRetryVersion] = useState(0)
  const [updatedAt, setUpdatedAt] = useState(null)
  const [modal, setModal] = useState(null)
  const [privacySuspended, setPrivacySuspended] = useState(false)
  const profileTriggerRef = useRef(null)
  const loadControllerRef = useRef(null)
  const loadGenerationRef = useRef(0)
  const snapshotKeyRef = useRef(null)

  const normalizedDraftQuery = query.trim()
  const queryIsValid = normalizedDraftQuery.length === 0 || normalizedDraftQuery.length >= 2

  useEffect(() => {
    if (!queryIsValid) return undefined
    const timer = window.setTimeout(() => {
      setDebouncedQuery(normalizedDraftQuery)
      setOffset(0)
    }, SEARCH_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [normalizedDraftQuery, queryIsValid])

  const contextKey = useMemo(() => resultContext({
    query: debouncedQuery,
    filters,
    offset,
  }), [debouncedQuery, filters, offset])
  const hasCurrentSnapshot = snapshotKey === contextKey
  const searchSettled = queryIsValid && normalizedDraftQuery === debouncedQuery
  const visibleResult = searchSettled && hasCurrentSnapshot ? result : null

  const load = useCallback(async () => {
    if (privacySuspended || !queryIsValid) return
    loadControllerRef.current?.abort()
    const controller = new AbortController()
    const generation = loadGenerationRef.current + 1
    const background = snapshotKeyRef.current === contextKey
    loadControllerRef.current = controller
    loadGenerationRef.current = generation
    if (background) setRefreshing(true)
    else setLoading(true)
    setLoadError(null)
    try {
      const response = await api('/crm/goscie/wyszukaj', 'POST', {
        q: debouncedQuery || null,
        vip: filters.vip === '' ? null : filters.vip === 'true',
        ryzyko: filters.ryzyko || null,
        min_wizyt: Number(filters.minWizyt) || 1,
        sort: filters.sort,
        offset,
        limit: PAGE_SIZE,
      }, { signal: controller.signal })
      if (controller.signal.aborted || loadGenerationRef.current !== generation) return
      setResult(normalizeResponse(response, offset))
      snapshotKeyRef.current = contextKey
      setSnapshotKey(contextKey)
      setUpdatedAt(new Date())
    } catch (error) {
      if (controller.signal.aborted || loadGenerationRef.current !== generation || error?.name === 'AbortError') return
      setLoadError(error.message || 'Nie udało się wczytać bazy gości.')
    } finally {
      if (loadGenerationRef.current !== generation) return
      loadControllerRef.current = null
      setLoading(false)
      setRefreshing(false)
    }
  }, [contextKey, debouncedQuery, filters, offset, privacySuspended, queryIsValid])

  useEffect(() => {
    void load()
    return () => {
      loadGenerationRef.current += 1
      loadControllerRef.current?.abort()
      loadControllerRef.current = null
    }
  }, [load, retryVersion])

  useEffect(() => subscribeReservationPrivacyPurge(() => {
    loadGenerationRef.current += 1
    loadControllerRef.current?.abort()
    loadControllerRef.current = null
    setPrivacySuspended(true)
    setQuery('')
    setDebouncedQuery('')
    setFilters(DEFAULT_FILTERS)
    setOffset(0)
    setResult(null)
    snapshotKeyRef.current = null
    setSnapshotKey(null)
    setModal(null)
    setLoading(false)
    setRefreshing(false)
    setLoadError(null)
    setUpdatedAt(null)
    profileTriggerRef.current = null
  }), [])

  const submit = (event) => {
    event.preventDefault()
    if (!queryIsValid) return
    setDebouncedQuery(normalizedDraftQuery)
    setOffset(0)
    if (normalizedDraftQuery === debouncedQuery && offset === 0) {
      setRetryVersion((value) => value + 1)
    }
  }

  const updateFilter = (name, value) => {
    setFilters((current) => ({ ...current, [name]: value }))
    setOffset(0)
  }

  const clearFilters = () => {
    setQuery('')
    setDebouncedQuery('')
    setFilters(DEFAULT_FILTERS)
    setOffset(0)
  }

  const activeFilters = Boolean(
    normalizedDraftQuery
    || filters.vip
    || filters.ryzyko
    || filters.minWizyt !== DEFAULT_FILTERS.minWizyt
    || filters.sort !== DEFAULT_FILTERS.sort,
  )
  const guests = visibleResult?.goscie || []
  const total = visibleResult?.total || 0
  const pageStart = total ? offset + 1 : 0
  const pageEnd = Math.min(offset + guests.length, total)

  return (
    <Card className="p-5 sm:p-8">
      <SectionHeader
        title="Baza gości"
        subtitle="Znajdź gościa, sprawdź historię wizyt i przygotuj obsługę przed kolejną rezerwacją."
      >
        <span className="inline-flex min-h-5 items-center gap-2 text-xs text-muted" role="status" aria-live="polite">
          {refreshing ? <><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Aktualizuję…</> : updatedAt ? `Aktualne z ${updatedAt.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}` : null}
        </span>
      </SectionHeader>

      <form onSubmit={submit} role="search" className="space-y-4 border-b border-line pb-5">
        <div className="grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_auto] lg:items-end">
          <div>
            <label className="field-label" htmlFor="crm-guest-query">Nazwisko, telefon lub e-mail</label>
            <div className="relative mt-1.5">
              <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input
                id="crm-guest-query"
                className="field pl-10"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="np. Kowalska lub 600 123 456"
                autoComplete="off"
                spellCheck="false"
                aria-invalid={!queryIsValid || undefined}
                aria-describedby="crm-query-help"
              />
            </div>
          </div>
          <Button type="submit" className="w-full lg:w-auto" disabled={!queryIsValid}>
            <Icon name="search" className="h-4 w-4" /> Szukaj
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-[repeat(4,minmax(0,auto))_1fr]">
          <label className="min-w-0">
            <span className="field-label">VIP</span>
            <select className="field mt-1.5" value={filters.vip} onChange={(event) => updateFilter('vip', event.target.value)}>
              <option value="">Wszyscy</option>
              <option value="true">Tylko VIP</option>
              <option value="false">Bez VIP</option>
            </select>
          </label>
          <label className="min-w-0">
            <span className="field-label">Ryzyko</span>
            <select className="field mt-1.5" value={filters.ryzyko} onChange={(event) => updateFilter('ryzyko', event.target.value)}>
              <option value="">Każde</option>
              <option value="wysokie">Wysokie</option>
              <option value="srednie">Średnie</option>
              <option value="niskie">Niskie</option>
            </select>
          </label>
          <label className="min-w-0">
            <span className="field-label">Minimum wizyt</span>
            <select className="field mt-1.5" value={filters.minWizyt} onChange={(event) => updateFilter('minWizyt', event.target.value)}>
              <option value="1">1 wizyta</option>
              <option value="2">2 wizyty</option>
              <option value="3">3 wizyty</option>
              <option value="5">5 wizyt</option>
            </select>
          </label>
          <label className="col-span-2 min-w-0 lg:col-span-1">
            <span className="field-label">Sortowanie</span>
            <select className="field mt-1.5" value={filters.sort} onChange={(event) => updateFilter('sort', event.target.value)}>
              <option value="ostatnia_data_desc">Ostatnio odwiedzający</option>
              <option value="wizyty_desc">Najwięcej wizyt</option>
              <option value="ryzyko_desc">Najwyższe ryzyko</option>
              <option value="nazwisko_asc">Nazwisko A–Z</option>
            </select>
          </label>
          {activeFilters ? (
            <Button variant="subtle" size="sm" className="col-span-2 justify-self-start lg:col-span-1 lg:justify-self-end" onClick={clearFilters}>
              <Icon name="close" className="h-4 w-4" /> Wyczyść filtry
            </Button>
          ) : null}
        </div>
        <p id="crm-query-help" className={`min-h-5 text-xs ${queryIsValid ? 'text-muted' : 'text-danger'}`} role={queryIsValid ? 'status' : 'alert'} aria-live="polite">
          {queryIsValid
            ? 'Fraza wyszukiwania pozostaje tylko w tym widoku i nie trafia do adresu ani historii przeglądarki.'
            : 'Wpisz co najmniej 2 znaki albo wyczyść pole.'}
        </p>
      </form>

      {loadError ? (
        <div role="alert" className="mt-5">
          <Banner variant="danger">
            <div className="flex flex-wrap items-center gap-3">
              <span>{loadError}{hasCurrentSnapshot ? ' Pokazujemy ostatnie wyniki dla tych filtrów.' : ''}</span>
              <Button variant="ghost" size="sm" onClick={() => setRetryVersion((value) => value + 1)}>Ponów</Button>
            </div>
          </Banner>
        </div>
      ) : null}

      <div className="mt-5" aria-busy={refreshing || (!hasCurrentSnapshot && loading) || undefined}>
        {!queryIsValid ? null : (!searchSettled || (!hasCurrentSnapshot && loading)) ? <CrmSkeleton /> : loadError && !hasCurrentSnapshot ? null : !visibleResult || guests.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line px-5 py-10 text-center">
            <p className="text-sm font-semibold text-ink">Brak pasujących gości</p>
            <p className="mt-1 text-sm text-muted">Zmień frazę lub filtry. Nowi goście pojawią się po zapisaniu rezerwacji.</p>
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th className="py-2 pr-3 font-semibold">Gość</th>
                    <th className="py-2 pr-3 font-semibold">Kontakt</th>
                    <th className="py-2 pr-3 text-right font-semibold">Wizyty</th>
                    <th className="py-2 pr-3 font-semibold">Ryzyko</th>
                    <th className="py-2 text-right font-semibold">Ostatnia</th>
                  </tr>
                </thead>
                <tbody>
                  {guests.map((guest) => (
                    <GuestTableRow key={guest.profil_ref} guest={guest} onOpen={(event) => {
                      profileTriggerRef.current = event.currentTarget
                      setModal({ reservationId: guest.profil_ref })
                    }} />
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="divide-y divide-line/70 md:hidden" aria-label="Wyniki wyszukiwania gości">
              {guests.map((guest) => (
                <li key={guest.profil_ref}>
                  <button
                    type="button"
                    onClick={(event) => {
                      profileTriggerRef.current = event.currentTarget
                      setModal({ reservationId: guest.profil_ref })
                    }}
                    className="flex min-h-20 w-full items-center gap-3 py-3 text-left transition active:scale-[0.995]"
                    aria-label={`Otwórz kartę gościa: ${guest.nazwisko || 'bez nazwiska'}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate font-semibold text-ink">{guest.nazwisko || 'Bez nazwiska'}</span>
                        {guest.vip ? <Pill className="bg-mint/15 text-mint">VIP</Pill> : null}
                        {guest.ma_alergie ? <Pill className="bg-danger/15 text-danger">Alergie</Pill> : null}
                      </div>
                      <p className="mt-1 truncate text-xs text-muted">{guest.telefon || guest.email || 'Brak kontaktu'}</p>
                      <p className="mt-1 text-xs text-muted">{guest.wizyt || 0} wizyt · {guest.no_show || 0} no-show · ostatnia {guest.ostatnia_data || '—'}</p>
                    </div>
                    <RiskPill value={guest.ryzyko} />
                    <Icon name="chevronDown" className="h-4 w-4 shrink-0 -rotate-90 text-muted" />
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {hasCurrentSnapshot && total > 0 ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
          <p className="text-xs text-muted">{pageStart}–{pageEnd} z {total}</p>
          <div className="flex gap-2">
            <Button variant="subtle" size="sm" disabled={offset === 0 || refreshing} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>Poprzednia</Button>
            <Button variant="subtle" size="sm" disabled={offset + PAGE_SIZE >= total || refreshing} onClick={() => setOffset((value) => value + PAGE_SIZE)}>Następna</Button>
          </div>
        </div>
      ) : null}

      {modal ? (
        <GuestProfileDialog
          reservationId={modal.reservationId}
          onClose={() => setModal(null)}
          onSaved={() => setRetryVersion((value) => value + 1)}
          restoreFocusRef={profileTriggerRef}
        />
      ) : null}
    </Card>
  )
}

function GuestTableRow({ guest, onOpen }) {
  return (
    <tr className="border-b border-line/60 transition hover:bg-white/[0.02]">
      <td className="py-2.5 pr-3">
        <button
          type="button"
          onClick={onOpen}
          className="-my-2 inline-flex min-h-11 items-center rounded-lg py-2 text-left font-semibold text-ink transition hover:text-mint"
          aria-label={`Otwórz kartę gościa: ${guest.nazwisko || 'bez nazwiska'}`}
        >
          {guest.nazwisko || 'Bez nazwiska'}
        </button>
        <div className="mt-1 flex flex-wrap gap-1">
          {guest.vip ? <Pill className="bg-mint/15 text-mint">VIP</Pill> : null}
          {guest.ma_alergie ? <Pill className="bg-danger/15 text-danger">Alergie</Pill> : null}
          {(guest.tagi || []).slice(0, 3).map((tag) => <Pill key={tag} className="bg-white/[0.06] text-muted">{tag}</Pill>)}
        </div>
      </td>
      <td className="py-2.5 pr-3 text-muted">{guest.telefon || guest.email || '—'}</td>
      <td className="py-2.5 pr-3 text-right tabular-nums text-ink">
        {guest.wizyt || 0}<span className="text-muted"> · {guest.no_show || 0} no-show</span>
      </td>
      <td className="py-2.5 pr-3"><RiskPill value={guest.ryzyko} /></td>
      <td className="py-2.5 text-right text-muted">{guest.ostatnia_data || '—'}</td>
    </tr>
  )
}

function RiskPill({ value = 'niskie' }) {
  return <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${RYZYKO[value] || RYZYKO.niskie}`}>{value}</span>
}

function Pill({ children, className }) {
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${className}`}>{children}</span>
}

function CrmSkeleton() {
  return (
    <div className="space-y-2" role="status" aria-label="Ładowanie bazy gości">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex min-h-16 animate-pulse items-center gap-4 border-b border-line/60 py-2 motion-reduce:animate-none">
          <span className="h-4 w-36 rounded bg-white/[0.07]" />
          <span className="h-4 w-28 rounded bg-white/[0.05]" />
          <span className="ml-auto h-4 w-20 rounded bg-white/[0.05]" />
        </div>
      ))}
      <span className="sr-only">Ładowanie gości…</span>
    </div>
  )
}
