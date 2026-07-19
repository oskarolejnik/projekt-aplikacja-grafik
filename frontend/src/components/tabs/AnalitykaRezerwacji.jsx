import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { PillSwitch } from '../ui/PillSwitch'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { warsawDateISO } from '../../lib/date'

const PRESETS = [
  { value: '7', label: '7 dni' },
  { value: '30', label: '30 dni' },
  { value: '90', label: '90 dni' },
  { value: 'custom', label: 'Własny' },
]

const VIEWS = [
  { value: 'overview', label: 'Przegląd' },
  { value: 'timing', label: 'Czas wizyt' },
  { value: 'utilization', label: 'Sale i stoły' },
]

const UTILIZATION_TYPES = [
  { value: 'sale', label: 'Sale' },
  { value: 'stoliki', label: 'Stoły' },
  { value: 'kombinacje', label: 'Konfiguracje' },
]

const CHANNEL_LABELS = {
  online: 'Online',
  reczna: 'Ręczna',
  google: 'Google',
  ical: 'iCal',
  walk_in: 'Walk-in',
}

const shiftDateIso = (iso, amount) => {
  const [year, month, day] = iso.split('-').map(Number)
  const value = new Date(Date.UTC(year, month - 1, day))
  value.setUTCDate(value.getUTCDate() + amount)
  return value.toISOString().slice(0, 10)
}

const presetRange = (days) => {
  const end = warsawDateISO()
  return { start: shiftDateIso(end, -(days - 1)), end }
}

const numberOrNull = (value) => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const formatMinutes = (value) => {
  const minutes = numberOrNull(value)
  if (minutes === null) return '—'
  if (minutes < 60) return `${Math.round(minutes)} min`
  const hours = Math.floor(minutes / 60)
  const rest = Math.round(minutes % 60)
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

const formatDelta = (value) => {
  const delta = numberOrNull(value)
  if (delta === null) return '—'
  if (delta === 0) return 'zgodnie z planem'
  return `${Math.abs(Math.round(delta))} min ${delta > 0 ? 'dłużej' : 'krócej'}`
}

const initialRange = presetRange(30)

export default function AnalitykaRezerwacji() {
  const [preset, setPreset] = useState('30')
  const [start, setStart] = useState(initialRange.start)
  const [end, setEnd] = useState(initialRange.end)
  const [view, setView] = useState('overview')
  const [utilizationType, setUtilizationType] = useState('sale')
  const [snapshot, setSnapshot] = useState(null)
  const [snapshotKey, setSnapshotKey] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [partialErrors, setPartialErrors] = useState([])
  const [updatedAt, setUpdatedAt] = useState(null)
  const [retryVersion, setRetryVersion] = useState(0)
  const requestRef = useRef({ generation: 0, controller: null })
  const snapshotKeyRef = useRef(null)
  const snapshotRef = useRef(null)

  const validRange = Boolean(start && end && start <= end)
  const contextKey = `${start}:${end}`
  const hasCurrentSnapshot = validRange && snapshotKey === contextKey
  const visibleSnapshot = hasCurrentSnapshot ? snapshot : null

  const load = useCallback(async () => {
    if (!validRange) return
    requestRef.current.controller?.abort()
    const controller = new AbortController()
    const generation = requestRef.current.generation + 1
    const background = snapshotKeyRef.current === contextKey
    requestRef.current = { generation, controller }
    if (background) setRefreshing(true)
    else setLoading(true)
    setError(null)
    setPartialErrors([])

    const suffix = `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    const requests = await Promise.allSettled([
      api(`/analityka/rezerwacje?${suffix}`, 'GET', null, { signal: controller.signal }),
      api(`/analityka/oblozenie?${suffix}`, 'GET', null, { signal: controller.signal }),
      api(`/analityka/rezerwacje/operacyjna?${suffix}`, 'GET', null, { signal: controller.signal }),
    ])
    if (controller.signal.aborted || requestRef.current.generation !== generation) return

    const labels = ['podsumowania', 'obłożenia', 'rzeczywistych czasów wizyt']
    const failures = requests
      .map((result, index) => result.status === 'rejected' ? labels[index] : null)
      .filter(Boolean)
    const [summary, occupancy, operational] = requests.map((result) => result.status === 'fulfilled' ? result.value : null)
    const hasAnyData = Boolean(summary || occupancy || operational)

    if (hasAnyData) {
      const previous = snapshotKeyRef.current === contextKey ? snapshotRef.current : null
      const nextSnapshot = {
        summary: summary ?? previous?.summary ?? null,
        occupancy: occupancy ?? previous?.occupancy ?? null,
        operational: operational ?? previous?.operational ?? null,
      }
      snapshotRef.current = nextSnapshot
      setSnapshot(nextSnapshot)
      snapshotKeyRef.current = contextKey
      setSnapshotKey(contextKey)
      setUpdatedAt(new Date())
      setPartialErrors(failures)
    } else {
      const firstError = requests.find((result) => result.status === 'rejected')?.reason
      setError(firstError?.message || 'Nie udało się wczytać wyników rezerwacji.')
    }
    if (requestRef.current.generation === generation) {
      requestRef.current.controller = null
      setLoading(false)
      setRefreshing(false)
    }
  }, [contextKey, end, start, validRange])

  useEffect(() => {
    void load()
    return () => {
      requestRef.current.generation += 1
      requestRef.current.controller?.abort()
      requestRef.current.controller = null
    }
  }, [load, retryVersion])

  useEffect(() => () => {
    requestRef.current.generation += 1
    requestRef.current.controller?.abort()
  }, [])

  const selectPreset = (value) => {
    setPreset(value)
    if (value === 'custom') return
    const range = presetRange(Number(value))
    setStart(range.start)
    setEnd(range.end)
  }

  return (
    <Card className="p-5 sm:p-8">
      <SectionHeader
        title="Wyniki rezerwacji"
        subtitle="Rzeczywiste czasy wizyt i wykorzystanie zasobów pomagają ocenić politykę lokalu bez automatycznej zmiany ustawień."
      >
        <Button variant="ghost" size="sm" onClick={() => setRetryVersion((value) => value + 1)} disabled={refreshing || !validRange}>
          {refreshing ? <Spinner className="h-4 w-4 motion-reduce:animate-none" /> : <Icon name="refresh" className="h-4 w-4" />}
          {refreshing ? 'Aktualizuję…' : 'Odśwież'}
        </Button>
      </SectionHeader>

      <div className="space-y-4 border-b border-line pb-5">
        <PillSwitch
          options={PRESETS}
          value={preset}
          onChange={selectPreset}
          label="Zakres wyników rezerwacji"
          className="w-full sm:max-w-lg"
        />
        {preset === 'custom' ? (
          <fieldset className="grid grid-cols-2 gap-3 sm:max-w-lg">
            <legend className="sr-only">Własny zakres dat</legend>
            <label className="min-w-0">
              <span className="field-label">Od</span>
              <input type="date" className="field mt-1.5 min-w-0" value={start} onChange={(event) => setStart(event.target.value)} />
            </label>
            <label className="min-w-0">
              <span className="field-label">Do</span>
              <input type="date" className="field mt-1.5 min-w-0" value={end} onChange={(event) => setEnd(event.target.value)} />
            </label>
          </fieldset>
        ) : null}
        <div className="flex min-h-5 flex-wrap items-center justify-between gap-2 text-xs text-muted" role="status" aria-live="polite">
          <span>{start && end ? `${start} – ${end}` : 'Wybierz zakres dat.'}</span>
          <span>{refreshing ? 'Poprzednie wyniki pozostają widoczne.' : updatedAt && hasCurrentSnapshot ? `${error ? 'Ostatni poprawny wynik' : partialErrors.length ? 'Częściowa aktualizacja' : 'Aktualne'} · ${updatedAt.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}` : null}</span>
        </div>
        {!validRange ? <p className="text-sm text-danger" role="alert">Data końcowa nie może być wcześniejsza niż początkowa.</p> : null}
      </div>

      {error ? (
        <div role="alert" className="mt-5">
          <Banner variant="danger">
            <div className="flex flex-wrap items-center gap-3">
              <span>{error}{hasCurrentSnapshot ? ' Pokazujemy ostatnie wyniki dla tego okresu.' : ''}</span>
              <Button variant="ghost" size="sm" onClick={() => setRetryVersion((value) => value + 1)}>Ponów</Button>
            </div>
          </Banner>
        </div>
      ) : null}

      {partialErrors.length ? (
        <div role="status" className="mt-5">
          <Banner variant="info">Nie udało się odświeżyć: {partialErrors.join(', ')}. Dla tego samego okresu pozostawiamy poprzedni poprawny wynik; brakującej wartości nigdy nie zastępujemy zerem.</Banner>
        </div>
      ) : null}

      {validRange && !hasCurrentSnapshot && loading ? <AnalyticsSkeleton /> : !visibleSnapshot ? null : (
        <div className="mt-5 space-y-6" aria-busy={refreshing || undefined}>
          <PillSwitch
            options={VIEWS}
            value={view}
            onChange={setView}
            label="Obszar wyników rezerwacji"
            className="w-full"
          />

          {view === 'overview' ? <Overview data={visibleSnapshot} /> : null}
          {view === 'timing' ? <TurnTimeView operational={visibleSnapshot.operational} /> : null}
          {view === 'utilization' ? (
            <UtilizationView
              operational={visibleSnapshot.operational}
              type={utilizationType}
              onTypeChange={setUtilizationType}
            />
          ) : null}

          <Banner variant="info">
            Wyniki są podpowiedzią do decyzji. Lokalo nie zmienia czasu wizyt ani zasad dostępności automatycznie.
          </Banner>
        </div>
      )}
    </Card>
  )
}

function Overview({ data }) {
  const hasSummary = Boolean(data.summary)
  const hasOccupancy = Boolean(data.occupancy)
  const hasOperational = Boolean(data.operational)
  const summary = data.summary || {}
  const occupancy = data.occupancy || {}
  const operational = data.operational || {}
  const quality = operational.jakosc_danych || {}
  const status = summary.statusy || {}
  const aggregate = occupancy.agregat || {}
  const turnTime = operational.turn_time || {}
  const channels = summary.kanaly || []
  const weekday = summary.szczyty?.wg_dnia_tygodnia || []

  return (
    <section aria-labelledby="reservation-overview-title" className="space-y-6">
      <div>
        <h3 id="reservation-overview-title" className="text-lg font-semibold text-ink">Najważniejsze fakty</h3>
        <p className="mt-1 text-sm text-muted">Najpierw skala ruchu i jakość pomiaru, później szczegóły.</p>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-5 border-y border-line py-5 lg:grid-cols-5">
        <Fact label="Zarezerwowane osoby" value={hasSummary ? (summary.covery?.suma ?? 0) : '—'} sub={hasSummary ? 'bez odwołanych; obejmuje no-show' : 'dane niedostępne'} />
        <Fact label="No-show" value={hasSummary ? `${status.no_show_proc ?? 0}%` : '—'} sub={hasSummary ? `${status.no_show ?? 0} wizyt` : 'dane niedostępne'} tone={hasSummary && (status.no_show_proc || 0) >= 15 ? 'danger' : undefined} />
        <Fact label="Zmierzono" value={hasOperational ? `${quality.z_pelnym_pomiarem ?? 0}/${quality.zakonczone_wizyty ?? 0}` : '—'} sub={hasOperational ? `${quality.kompletnosc_proc ?? 0}% próby` : 'dane niedostępne'} />
        <Fact label="Mediana wizyty" value={hasOperational ? formatMinutes(turnTime.mediana_min) : '—'} sub={hasOperational ? `plan ${formatMinutes(turnTime.planowana_mediana_min)}` : 'dane niedostępne'} />
        <Fact label="Planowane obłożenie stołów" value={hasOccupancy ? `${aggregate.oblozenie_stolowe_proc ?? 0}%` : '—'} sub={hasOccupancy ? 'wg ustawionych czasów wizyt' : 'dane niedostępne'} />
      </dl>

      <div className="grid gap-6 lg:grid-cols-2">
        <DataSection title="Źródła rezerwacji" empty={!channels.length} unavailable={!hasSummary}>
          {channels.map((channel) => (
            <DataBar
              key={channel.kanal}
              label={CHANNEL_LABELS[channel.kanal] || channel.kanal}
              value={channel.proc || 0}
              max={100}
              suffix={`${channel.proc || 0}% · ${channel.liczba || 0}`}
            />
          ))}
        </DataSection>
        <DataSection title="Ruch według dnia tygodnia" empty={!weekday.some((row) => row.covery)} unavailable={!hasSummary}>
          {weekday.map((row) => (
            <DataBar
              key={row.dzien}
              label={row.dzien}
              value={row.covery || 0}
              max={Math.max(1, ...weekday.map((entry) => entry.covery || 0))}
              suffix={`${row.covery || 0} os.`}
            />
          ))}
        </DataSection>
      </div>
    </section>
  )
}

function TurnTimeView({ operational }) {
  if (!operational) {
    return (
      <section aria-labelledby="turn-time-title-unavailable" className="space-y-5">
        <div>
          <h3 id="turn-time-title-unavailable" className="text-lg font-semibold text-ink">Rzeczywisty czas wizyt</h3>
          <p className="mt-1 text-sm text-muted">Pomiar obejmuje wyłącznie wizyty z poprawnym posadzeniem i wyjściem.</p>
        </div>
        <Banner variant="info">Dane o czasie wizyt są chwilowo niedostępne dla tego okresu.</Banner>
      </section>
    )
  }
  const quality = operational?.jakosc_danych || {}
  const turnTime = operational?.turn_time || {}
  const groups = (turnTime.wg_wielkosci_grupy || []).filter((row) => Number(row.proba) > 0)
  const incomplete = Number(quality.zakonczone_wizyty) > 0 && (quality.kompletnosc_proc ?? 0) < 60

  return (
    <section aria-labelledby="turn-time-title" className="space-y-5">
      <div>
        <h3 id="turn-time-title" className="text-lg font-semibold text-ink">Rzeczywisty czas wizyt</h3>
        <p className="mt-1 text-sm text-muted">Pomiar obejmuje wyłącznie wizyty z poprawnym posadzeniem i wyjściem.</p>
      </div>
      {incomplete ? (
        <Banner variant="warn">Kompletność próby wynosi {quality.kompletnosc_proc ?? 0}%. Traktuj różnice jako wstępną obserwację.</Banner>
      ) : null}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-5 border-y border-line py-5 sm:grid-cols-4">
        <Fact as="div" label="Pełne pomiary" value={quality.z_pelnym_pomiarem ?? 0} sub={`z ${quality.zakonczone_wizyty ?? 0} zakończonych`} />
        <Fact as="div" label="Bez pomiaru" value={quality.bez_pomiaru ?? 0} />
        <Fact as="div" label="Błędny pomiar" value={quality.nieprawidlowy_pomiar ?? 0} />
        <Fact as="div" label="Pominięte przeniesienia" value={quality.pominiete_przeniesienia ?? 0} />
      </dl>

      {!groups.length ? <EmptyState text="Brak pełnych pomiarów w tym okresie." /> : (
        <>
          <div className="hidden overflow-hidden rounded-xl border border-line sm:block">
            <table className="w-full text-sm">
              <thead className="bg-white/[0.025] text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-3 font-semibold">Grupa</th>
                  <th className="px-4 py-3 text-right font-semibold">Próba</th>
                  <th className="px-4 py-3 text-right font-semibold">Plan</th>
                  <th className="px-4 py-3 text-right font-semibold">Mediana</th>
                  <th className="px-4 py-3 text-right font-semibold">Różnica</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/70">
                {groups.map((row) => (
                  <tr key={row.grupa}>
                    <td className="px-4 py-3 font-semibold text-ink">{row.grupa} os.</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{row.proba || 0}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{formatMinutes(row.planowana_mediana_min)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-ink">{formatMinutes(row.mediana_min)}</td>
                    <td className="px-4 py-3 text-right text-muted">{formatDelta(row.odchylenie_min)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="divide-y divide-line/70 sm:hidden" aria-label="Czas wizyt według wielkości grupy">
            {groups.map((row) => (
              <li key={row.grupa} className="py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-ink">{row.grupa} os.</span>
                  <span className="text-xs text-muted">{row.proba || 0} pomiarów</span>
                </div>
                <p className="mt-1 text-sm text-muted">Mediana <b className="font-semibold text-ink">{formatMinutes(row.mediana_min)}</b> · plan {formatMinutes(row.planowana_mediana_min)}</p>
                <p className="mt-1 text-xs text-muted">{formatDelta(row.odchylenie_min)}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function UtilizationView({ operational, type, onTypeChange }) {
  if (!operational) {
    return (
      <section aria-labelledby="utilization-title-unavailable" className="space-y-5">
        <div>
          <h3 id="utilization-title-unavailable" className="text-lg font-semibold text-ink">Wykorzystanie sali</h3>
          <p className="mt-1 text-sm text-muted">Liczba wizyt i zmierzony czas zajęcia — bez dopisywania brakujących minut.</p>
        </div>
        <Banner variant="info">Dane o wykorzystaniu sal i stołów są chwilowo niedostępne dla tego okresu.</Banner>
      </section>
    )
  }
  const utilization = operational?.wykorzystanie || {}
  const rows = utilization[type] || []
  const unassigned = utilization.bez_przydzialu || {}

  return (
    <section aria-labelledby="utilization-title" className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 id="utilization-title" className="text-lg font-semibold text-ink">Wykorzystanie sali</h3>
          <p className="mt-1 text-sm text-muted">Liczba wizyt i zmierzony czas zajęcia — bez dopisywania brakujących minut.</p>
        </div>
        <label className="sm:min-w-48">
          <span className="field-label">Zasób</span>
          <select className="field mt-1.5" value={type} onChange={(event) => onTypeChange(event.target.value)}>
            {UTILIZATION_TYPES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
      </div>

      {!rows.length ? <EmptyState text="Brak zmierzonych wizyt dla tego rodzaju zasobu." /> : (
        <ul className="divide-y divide-line/70 border-y border-line" aria-label={`Wykorzystanie: ${UTILIZATION_TYPES.find((option) => option.value === type)?.label}`}>
          {rows.map((row, index) => {
            const name = row.nazwa || `Pozycja ${index + 1}`
            const tableNames = (row.stoliki || []).map((table) => table.nazwa).filter(Boolean).join(' + ')
            const context = [row.sala_nazwa, type === 'kombinacje' ? tableNames : null].filter(Boolean).join(' · ')
            return (
              <li key={`${type}:${row.sala_id || ''}:${row.stolik_id || row.kombinacja_id || index}`} className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_repeat(3,auto)] sm:items-center sm:gap-6">
                <div className="min-w-0">
                  <p className="truncate font-semibold text-ink">{name}</p>
                  {context ? <p className="mt-0.5 truncate text-xs text-muted">{context}</p> : null}
                </div>
                <UtilizationValue label="Wizyty" value={row.wizyty || 0} />
                <UtilizationValue label="Goście" value={row.covery || 0} />
                <UtilizationValue label="Zmierzony czas" value={formatMinutes(row.rzeczywiste_minuty)} />
              </li>
            )
          })}
        </ul>
      )}

      {(unassigned.wizyty || 0) > 0 ? (
        <Banner variant="info">{unassigned.wizyty} wizyt nie ma historycznego przydziału i nie zostało dopisanych do żadnej sali ani stołu.</Banner>
      ) : null}
    </section>
  )
}

function Fact({ label, value, sub, tone, as: Element = 'div' }) {
  return (
    <Element className="min-w-0">
      <dt className="text-xs font-semibold text-muted">{label}</dt>
      <dd className={`mt-1 text-xl font-semibold tabular-nums ${tone === 'danger' ? 'text-danger' : 'text-ink'}`}>{value}</dd>
      {sub ? <dd className="mt-0.5 text-xs text-muted">{sub}</dd> : null}
    </Element>
  )
}

function UtilizationValue({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm sm:block sm:text-right">
      <span className="text-xs text-muted sm:block">{label}</span>
      <span className="font-semibold tabular-nums text-ink">{value}</span>
    </div>
  )
}

function DataSection({ title, empty, unavailable = false, children }) {
  return (
    <section className="border-t border-line pt-5">
      <h4 className="mb-3 text-sm font-semibold text-ink">{title}</h4>
      {unavailable ? <p className="text-sm text-muted">Dane są chwilowo niedostępne.</p> : empty ? <p className="text-sm text-muted">Brak danych w tym okresie.</p> : <div className="space-y-2">{children}</div>}
    </section>
  )
}

function DataBar({ label, value, max, suffix }) {
  const percent = Math.round((Number(value) / Math.max(1, Number(max))) * 100)
  return (
    <div className="grid grid-cols-[5rem_minmax(0,1fr)_auto] items-center gap-3 text-xs">
      <span className="truncate text-muted">{label}</span>
      <span className="h-2 overflow-hidden rounded-full bg-white/[0.05]" aria-hidden="true">
        <span className="block h-full rounded-full bg-mint/60" style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
      </span>
      <span className="text-right tabular-nums text-muted">{suffix}</span>
    </div>
  )
}

function EmptyState({ text }) {
  return <div className="rounded-xl border border-dashed border-line px-5 py-10 text-center text-sm text-muted">{text}</div>
}

function AnalyticsSkeleton() {
  return (
    <div className="mt-5 space-y-5" role="status" aria-label="Ładowanie wyników rezerwacji">
      <div className="h-14 animate-pulse rounded-2xl bg-white/[0.05] motion-reduce:animate-none" />
      <div className="grid grid-cols-2 gap-4 border-y border-line py-5 lg:grid-cols-5">
        {[0, 1, 2, 3, 4].map((item) => <span key={item} className="h-14 animate-pulse rounded-xl bg-white/[0.04] motion-reduce:animate-none" />)}
      </div>
      <span className="sr-only">Ładowanie wyników…</span>
    </div>
  )
}
