import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { PillSwitch } from '../ui/PillSwitch'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { useAuth } from '../../context/AuthContext'
import { warsawDateISO } from '../../lib/date'
import { shiftDateIso } from '../../lib/reservationRoute'
import { readHostSnapshotCache, writeHostSnapshotCache } from '../../lib/hostSnapshotCache'
import HostFloorPlan from './HostFloorPlan'
import HostTimeline from './HostTimeline'

const POLL_INTERVAL_MS = 30000
const CLOCK_INTERVAL_MS = 30000
const HOST_ON_FLOOR = new Set(['posadzony', 'rachunek', 'oplacony'])
const HOST_FINISHED = new Set(['wyszedl'])
const RESERVATION_FINISHED = new Set(['odbyla', 'no_show'])
const dzisISO = () => warsawDateISO()
const fld = 'rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink outline-none transition focus:border-mint/60 focus:ring-2 focus:ring-mint/20'

const FAZA_META = {
  posadzony: { label: 'Na sali', className: 'bg-mint/12 text-mint' },
  rachunek: { label: 'Rachunek', className: 'bg-lemon/12 text-lemon' },
  oplacony: { label: 'Opłacony', className: 'bg-white/[0.08] text-ink' },
}

const MOBILE_VIEWS = [
  { value: 'guests', label: 'Goście' },
  { value: 'floor', label: 'Sala' },
  { value: 'timeline', label: 'Czas' },
]

const isOnline = () => typeof navigator === 'undefined' || navigator.onLine !== false
const isVisible = () => typeof document === 'undefined' || document.visibilityState !== 'hidden'

const tableIdsFor = (reservation) => [
  reservation?.stolik_id,
  ...(reservation?.stoliki_dodatkowe || []),
].filter(Boolean)

const queueGroupFor = (reservation) => {
  if (HOST_FINISHED.has(reservation?.faza_hosta) || RESERVATION_FINISHED.has(reservation?.status)) return 'zakonczone'
  if (HOST_ON_FLOOR.has(reservation?.faza_hosta)) return 'na_sali'
  return 'nadchodzace'
}

const sortByTime = (entries) => [...entries].sort((first, second) => (
  String(first.godz_od || '').localeCompare(String(second.godz_od || '')) || first.id - second.id
))

const queueSummary = (queue) => ({
  nadchodzace: queue.nadchodzace.length,
  na_sali: queue.na_sali.length,
  zakonczone: queue.zakonczone.length,
  waitlista: queue.waitlista.length,
  coverow_na_sali: queue.na_sali.reduce((sum, entry) => sum + (entry.liczba_osob || 0), 0),
})

function patchSnapshotReservation(snapshot, response) {
  if (!snapshot?.kolejka || !response?.id) return snapshot
  const groups = ['nadchodzace', 'na_sali', 'zakonczone']
  const previous = groups
    .flatMap((group) => snapshot.kolejka[group] || [])
    .find((entry) => entry.id === response.id)
  const reservation = {
    ...previous,
    ...response,
    minuty_od_posadzenia: response.minuty_od_posadzenia
      ?? (response.faza_hosta === 'posadzony' && previous?.faza_hosta !== 'posadzony' ? 0 : previous?.minuty_od_posadzenia),
  }
  const nextQueue = {
    ...snapshot.kolejka,
    waitlista: snapshot.kolejka.waitlista || [],
  }
  for (const group of groups) {
    nextQueue[group] = (snapshot.kolejka[group] || []).filter((entry) => entry.id !== response.id)
  }
  const target = queueGroupFor(reservation)
  nextQueue[target] = sortByTime([...nextQueue[target], reservation])
  nextQueue.podsumowanie = queueSummary(nextQueue)

  const oldOccupancies = snapshot.os_czasu?.zajetosci || []
  const template = oldOccupancies.find((entry) => entry.rezerwacja_id === response.id)
  const remaining = oldOccupancies.filter((entry) => entry.rezerwacja_id !== response.id)
  const activeOnTimeline = !HOST_FINISHED.has(reservation.faza_hosta)
    && !RESERVATION_FINISHED.has(reservation.status)
    && reservation.status !== 'odwolana'
  const occupancies = activeOnTimeline
    ? tableIdsFor(reservation).map((tableId) => ({
        ...template,
        stolik_id: tableId,
        rezerwacja_id: reservation.id,
        godz_od: reservation.godz_od || template?.godz_od,
        godz_do: reservation.godz_do || template?.godz_do,
        nazwisko: reservation.nazwisko || template?.nazwisko || 'Gość',
        liczba_osob: reservation.liczba_osob,
        faza_hosta: reservation.faza_hosta,
      })).filter((entry) => entry.godz_od && entry.godz_do)
    : []

  return {
    ...snapshot,
    kolejka: nextQueue,
    os_czasu: snapshot.os_czasu
      ? { ...snapshot.os_czasu, zajetosci: [...remaining, ...occupancies] }
      : snapshot.os_czasu,
  }
}

const formatFreshness = (generatedAt, stale = false) => {
  const date = generatedAt ? new Date(generatedAt) : null
  if (!date || Number.isNaN(date.getTime())) return 'Czas aktualizacji nieznany'
  return `${stale ? 'Dane z' : 'Aktualne'} ${new Intl.DateTimeFormat('pl-PL', {
    timeZone: 'Europe/Warsaw',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)}`
}

const warsawClockMinutes = (now) => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Warsaw',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now).map(({ type, value }) => [type, value]))
  return Number(parts.hour) * 60 + Number(parts.minute)
}

const clockMinutes = (value) => {
  const [hour, minute] = String(value || '').split(':').map(Number)
  return Number.isFinite(hour) && Number.isFinite(minute) ? hour * 60 + minute : null
}

const visitTiming = (reservation, day, nowMs) => {
  const seatedMinutes = reservation.minuty_od_posadzenia
  const now = new Date(nowMs)
  if (day === warsawDateISO(now) && reservation.godz_do) {
    const start = clockMinutes(reservation.godz_od)
    let end = clockMinutes(reservation.godz_do)
    let current = warsawClockMinutes(now)
    if (end != null) {
      if (start != null && end <= start) end += 1440
      if (end > 1440 && current < (start ?? 0)) current += 1440
      const remaining = end - current
      if (remaining < 0) return { text: `${Math.abs(remaining)} min po planie`, className: 'text-danger' }
      if (remaining <= 20) return { text: `${remaining} min do końca`, className: 'text-lemon' }
    }
  }
  return {
    text: seatedMinutes != null ? `${seatedMinutes} min na sali` : 'Wizyta trwa',
    className: 'text-mint',
  }
}

export default function WidokHosta({ date: controlledDate, onDateChange, active = true } = {}) {
  const { user, can, isAdmin } = useAuth()
  const canViewSensitive = isAdmin || can('rezerwacje.dane_wrazliwe')
  const canViewContacts = isAdmin || can('rezerwacje.dane_kontaktowe')
  const dateControlled = controlledDate !== undefined
  const [localDate, setLocalDate] = useState(dzisISO())
  const data = dateControlled ? controlledDate : localDate
  const dataRef = useRef(data)
  const [snapshot, setSnapshot] = useState(null)
  const snapshotRef = useRef(null)
  const snapshotClockBaseRef = useRef(Date.now())
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)
  const [connection, setConnection] = useState(isOnline() ? 'online' : 'offline')
  const [cached, setCached] = useState(false)
  const [mobileView, setMobileView] = useState('guests')
  const [pick, setPick] = useState({})
  const [actions, setActions] = useState({})
  const [rowFeedback, setRowFeedback] = useState({})
  const [clockNow, setClockNow] = useState(Date.now())
  const requestId = useRef(0)
  const loadControllerRef = useRef(null)
  const hasDataRef = useRef(false)
  const mutationGenerationRef = useRef(0)
  const mutationControllersRef = useRef(new Set())

  const cancelReadRequests = useCallback(() => {
    requestId.current += 1
    loadControllerRef.current?.abort()
    loadControllerRef.current = null
  }, [])

  const cancelMutationContinuations = useCallback(() => {
    mutationGenerationRef.current += 1
    mutationControllersRef.current.forEach((controller) => controller.abort())
    mutationControllersRef.current.clear()
  }, [])

  const acceptSnapshot = useCallback((next, { fromCache = false, persist = false } = {}) => {
    if (!next || next.schema_version !== 1 || next.data !== dataRef.current) {
      throw new Error('Serwer zwrócił niezgodny snapshot widoku hosta.')
    }
    snapshotRef.current = next
    snapshotClockBaseRef.current = Number.isFinite(Date.parse(next.generated_at))
      ? Date.parse(next.generated_at)
      : Date.now()
    hasDataRef.current = true
    setSnapshot(next)
    setCached(fromCache)
    setClockNow(Date.now())
    if (persist) writeHostSnapshotCache(user, next)
  }, [user])

  const restoreCachedSnapshot = useCallback((day) => {
    const saved = readHostSnapshotCache(user, day)
    if (!saved) return false
    acceptSnapshot(saved, { fromCache: true })
    return true
  }, [acceptSnapshot, user])

  const load = useCallback(async ({ quiet = false, day = dataRef.current } = {}) => {
    if (!active || !isVisible() || day !== dataRef.current) return
    if (!isOnline()) {
      setConnection('offline')
      const message = 'Brak połączenia. Pokazujemy ostatni bezpieczny podgląd tylko do odczytu.'
      setRefreshing(false)
      setRefreshError(hasDataRef.current ? message : null)
      if (!hasDataRef.current && !restoreCachedSnapshot(day)) {
        setLoadError('Brak połączenia i zapisanego podglądu dla tego dnia.')
        setLoading(false)
      }
      return
    }

    loadControllerRef.current?.abort()
    const controller = new AbortController()
    loadControllerRef.current = controller
    const id = ++requestId.current
    if (quiet || hasDataRef.current) {
      setRefreshing(true)
      setRefreshError(null)
    } else {
      setLoading(true)
      setLoadError(null)
    }
    try {
      const next = await api(`/host/snapshot?data=${encodeURIComponent(day)}`, 'GET', null, {
        signal: controller.signal,
      })
      if (controller.signal.aborted || id !== requestId.current || day !== dataRef.current) return
      acceptSnapshot(next, { persist: true })
      setConnection('online')
      setLoadError(null)
      setRefreshError(null)
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError' || id !== requestId.current || day !== dataRef.current) return
      const message = error.message || 'Nie udało się pobrać widoku hosta.'
      setConnection(isOnline() ? 'stale' : 'offline')
      if (hasDataRef.current) {
        setRefreshError(message)
      } else if (restoreCachedSnapshot(day)) {
        setRefreshError(`Nie udało się połączyć z serwerem. ${message}`)
      } else {
        setLoadError(message)
      }
    } finally {
      if (controller.signal.aborted || id !== requestId.current || day !== dataRef.current) return
      if (loadControllerRef.current === controller) loadControllerRef.current = null
      setRefreshing(false)
      setLoading(false)
    }
  }, [acceptSnapshot, active, restoreCachedSnapshot])

  useEffect(() => {
    const purge = () => {
      cancelReadRequests()
      cancelMutationContinuations()
      snapshotRef.current = null
      hasDataRef.current = false
      setSnapshot(null)
      setPick({})
      setActions({})
      setRowFeedback({})
      setRefreshing(false)
    }
    const unsubscribe = subscribeReservationPrivacyPurge(purge)
    return () => {
      unsubscribe()
      purge()
    }
  }, [cancelMutationContinuations, cancelReadRequests])

  useEffect(() => {
    if (!data || dataRef.current === data) return
    dataRef.current = data
    cancelReadRequests()
    hasDataRef.current = false
    snapshotRef.current = null
    setSnapshot(null)
    setCached(false)
    setLoading(true)
    setLoadError(null)
    setRefreshError(null)
    setRefreshing(false)
    setPick({})
    setRowFeedback({})
    if (active && isVisible()) void load({ day: data })
  }, [active, cancelReadRequests, data, load])

  useEffect(() => {
    if (!active) {
      cancelReadRequests()
      setRefreshing(false)
      return undefined
    }
    let pollId = null
    const stopPolling = () => {
      if (pollId != null) window.clearInterval(pollId)
      pollId = null
    }
    const startPolling = ({ immediate = true } = {}) => {
      stopPolling()
      if (!isVisible()) {
        cancelReadRequests()
        setRefreshing(false)
        return
      }
      if (immediate) void load({ quiet: hasDataRef.current })
      pollId = window.setInterval(() => {
        if (isVisible() && isOnline()) void load({ quiet: true })
      }, POLL_INTERVAL_MS)
    }
    const onVisibilityChange = () => startPolling({ immediate: isVisible() })
    const onOnline = () => {
      // Zapisy pozostają zablokowane, dopóki świeży snapshot nie potwierdzi stanu serwera.
      setConnection('stale')
      startPolling({ immediate: true })
    }
    const onOffline = () => {
      setConnection('offline')
      cancelReadRequests()
      setRefreshing(false)
      const message = 'Brak połączenia. Widok działa tylko do odczytu do czasu synchronizacji.'
      if (hasDataRef.current) {
        setRefreshError(message)
        return
      }
      const restored = restoreCachedSnapshot(dataRef.current)
      setLoading(false)
      if (restored) {
        setRefreshError(message)
      } else {
        setRefreshError(null)
        setLoadError('Brak połączenia i zapisanego podglądu dla tego dnia.')
      }
    }

    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    startPolling()
    return () => {
      stopPolling()
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      cancelReadRequests()
      setRefreshing(false)
    }
  }, [active, cancelReadRequests, load, restoreCachedSnapshot])

  useEffect(() => {
    if (!active || !snapshot) return undefined
    const tick = () => {
      if (isVisible()) setClockNow(Date.now())
    }
    const intervalId = window.setInterval(tick, CLOCK_INTERVAL_MS)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [active, snapshot])

  const changeDay = (nextDay) => {
    if (!nextDay || nextDay === data) return
    onDateChange?.(nextDay)
    if (dateControlled) return
    dataRef.current = nextDay
    cancelReadRequests()
    hasDataRef.current = false
    snapshotRef.current = null
    setSnapshot(null)
    setCached(false)
    setLoading(true)
    setLoadError(null)
    setRefreshError(null)
    setRefreshing(false)
    setPick({})
    setRowFeedback({})
    setLocalDate(nextDay)
  }

  const startMutation = () => {
    const controller = new AbortController()
    mutationControllersRef.current.add(controller)
    return { controller, generation: mutationGenerationRef.current }
  }
  const mutationIsCurrent = ({ controller, generation }) => (
    !controller.signal.aborted && generation === mutationGenerationRef.current
  )
  const finishMutation = ({ controller }) => mutationControllersRef.current.delete(controller)
  const readOnly = cached || connection !== 'online' || Boolean(refreshError)

  const applyMutationResponse = (response) => {
    const patched = patchSnapshotReservation(snapshotRef.current, response)
    snapshotRef.current = patched
    snapshotClockBaseRef.current = Date.now()
    setSnapshot(patched)
    setClockNow(Date.now())
  }

  const posadz = async (reservation) => {
    if (actions[reservation.id] || readOnly) return
    const operationDay = dataRef.current
    cancelReadRequests()
    setActions((current) => ({ ...current, [reservation.id]: 'seat' }))
    setRowFeedback((current) => ({ ...current, [reservation.id]: null }))
    const mutation = startMutation()
    try {
      const tableId = pick[reservation.id]
      const response = await api(`/host/rezerwacja/${reservation.id}/posadz`, 'POST', {
        stolik_id: tableId ? Number(tableId) : null,
      }, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      applyMutationResponse(response)
      setPick((current) => ({ ...current, [reservation.id]: '' }))
      setRowFeedback((current) => ({
        ...current,
        [reservation.id]: { type: 'success', message: 'Posadzono gości. Widok synchronizuje się w tle.' },
      }))
      void load({ quiet: true, day: operationDay })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      const resultUnknown = error?.status == null
      if (resultUnknown) {
        setConnection(isOnline() ? 'stale' : 'offline')
        setRefreshError('Nie udało się potwierdzić wyniku ostatniej akcji. Odśwież widok przed kolejnym zapisem.')
      }
      setRowFeedback((current) => ({
        ...current,
        [reservation.id]: resultUnknown ? {
          type: 'error',
          message: 'Połączenie zostało przerwane. Nie znamy wyniku — odśwież widok przed ponowieniem.',
        } : {
          type: 'error',
          message: error.message || 'Nie udało się posadzić gości.',
          retry: { type: 'seat' },
        },
      }))
    } finally {
      finishMutation(mutation)
      if (!mutationIsCurrent(mutation)) return
      setActions((current) => {
        const next = { ...current }
        delete next[reservation.id]
        return next
      })
    }
  }

  const changePhase = async (reservation, phase) => {
    if (actions[reservation.id] || readOnly) return
    const operationDay = dataRef.current
    cancelReadRequests()
    setActions((current) => ({ ...current, [reservation.id]: phase }))
    setRowFeedback((current) => ({ ...current, [reservation.id]: null }))
    const mutation = startMutation()
    try {
      const response = await api(`/host/rezerwacja/${reservation.id}/faza`, 'POST', { faza: phase }, {
        signal: mutation.controller.signal,
      })
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      applyMutationResponse(response)
      setRowFeedback((current) => ({
        ...current,
        [reservation.id]: { type: 'success', message: phase === 'wyszedl' ? 'Wizyta zakończona.' : 'Etap wizyty zaktualizowany.' },
      }))
      void load({ quiet: true, day: operationDay })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      const resultUnknown = error?.status == null
      if (resultUnknown) {
        setConnection(isOnline() ? 'stale' : 'offline')
        setRefreshError('Nie udało się potwierdzić wyniku ostatniej akcji. Odśwież widok przed kolejnym zapisem.')
      }
      setRowFeedback((current) => ({
        ...current,
        [reservation.id]: resultUnknown ? {
          type: 'error',
          message: 'Połączenie zostało przerwane. Nie znamy wyniku — odśwież widok przed ponowieniem.',
        } : {
          type: 'error',
          message: error.message || 'Nie udało się zmienić etapu wizyty.',
          retry: { type: 'phase', phase },
        },
      }))
    } finally {
      finishMutation(mutation)
      if (!mutationIsCurrent(mutation)) return
      setActions((current) => {
        const next = { ...current }
        delete next[reservation.id]
        return next
      })
    }
  }

  const liveQueue = useMemo(() => {
    if (!snapshot?.kolejka) return null
    const elapsed = Math.max(0, Math.floor((clockNow - snapshotClockBaseRef.current) / 60000))
    return {
      ...snapshot.kolejka,
      na_sali: (snapshot.kolejka.na_sali || []).map((reservation) => ({
        ...reservation,
        minuty_od_posadzenia: reservation.minuty_od_posadzenia == null
          ? null
          : reservation.minuty_od_posadzenia + elapsed,
      })),
    }
  }, [clockNow, snapshot])

  const dataLabel = new Date(`${data}T12:00:00`).toLocaleDateString('pl-PL', {
    weekday: 'long', day: 'numeric', month: 'long',
  })
  const summary = liveQueue?.podsumowanie || {}
  const retryRowAction = (reservation, retry) => {
    if (retry?.type === 'seat') return posadz(reservation)
    if (retry?.type === 'phase') return changePhase(reservation, retry.phase)
    return undefined
  }

  return (
    <Card className="overflow-hidden">
      <div className="p-4 sm:p-6 lg:p-7">
        <SectionHeader
          title="Serwis na żywo"
          subtitle="Plan sali, kolejka i oś czasu korzystają z tego samego snapshotu. Zmiany zapisują się przy konkretnym gościu."
        >
          <div className="flex max-w-full flex-wrap items-center gap-2">
            <button type="button" onClick={() => changeDay(shiftDateIso(data, -1))} aria-label="Poprzedni dzień" className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-line text-lg text-muted transition hover:bg-white/[0.05] hover:text-ink active:scale-[0.98]">‹</button>
            <label className="sr-only" htmlFor="host-day">Dzień widoku hosta</label>
            <input id="host-day" type="date" value={data} onChange={(event) => changeDay(event.target.value)} className={`${fld} min-h-11 min-w-0 max-w-[10.5rem]`} />
            <button type="button" onClick={() => changeDay(shiftDateIso(data, 1))} aria-label="Następny dzień" className="grid min-h-11 min-w-11 place-items-center rounded-xl border border-line text-lg text-muted transition hover:bg-white/[0.05] hover:text-ink active:scale-[0.98]">›</button>
            <Button variant="subtle" size="sm" onClick={() => changeDay(dzisISO())}>Dzisiaj</Button>
          </div>
        </SectionHeader>

        {snapshot ? (
          <div className="flex flex-col gap-3 border-y border-line py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <Metric value={summary.nadchodzace ?? 0} label="nadchodzi" />
              <Metric value={summary.na_sali ?? 0} label="na sali" accent />
              <Metric value={summary.coverow_na_sali ?? 0} label="gości na sali" />
              <Metric value={summary.waitlista ?? liveQueue?.waitlista?.length ?? 0} label="oczekuje" />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="capitalize">{dataLabel}</span>
              <span aria-hidden>·</span>
              <time dateTime={snapshot.generated_at}>{formatFreshness(snapshot.generated_at, readOnly)}</time>
              <span className="inline-flex min-h-5 items-center gap-1.5" aria-hidden="true">
                {refreshing ? <><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Odświeżam…</> : null}
              </span>
            </div>
          </div>
        ) : null}

        {refreshError && snapshot ? (
          <Banner variant="warn" className="mt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>{cached ? 'Bezpieczny podgląd offline ukrywa dane osobowe. ' : ''}{refreshError} Zapisy są chwilowo wyłączone.</span>
              <Button variant="ghost" size="sm" onClick={() => load({ quiet: true })} disabled={!isOnline()}>Ponów</Button>
            </div>
          </Banner>
        ) : null}

        {loading && !snapshot ? (
          <HostSkeleton />
        ) : loadError && !snapshot ? (
          <div className="mt-5" role="alert">
            <Banner variant="danger">
              <div className="space-y-3">
                <p>Nie udało się pobrać serwisu: {loadError}</p>
                <Button variant="ghost" size="sm" onClick={() => load()} disabled={!isOnline()}>Spróbuj ponownie</Button>
              </div>
            </Banner>
          </div>
        ) : snapshot ? (
          <div className="mt-5">
            <PillSwitch
              className="mb-5 lg:hidden"
              options={MOBILE_VIEWS}
              value={mobileView}
              onChange={setMobileView}
              label="Widok serwisu"
            />

            <div className="lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(22rem,0.65fr)]">
              <div
                className={`${mobileView === 'floor' ? 'block' : 'hidden'} min-w-0 lg:block lg:pr-6`}
              >
                <HostFloorPlan
                  floor={snapshot.plan_sali}
                  queue={liveQueue}
                  offline={readOnly}
                  canViewContacts={canViewContacts}
                />
              </div>
              <div
                className={`${mobileView === 'guests' ? 'block' : 'hidden'} min-w-0 lg:block lg:border-l lg:border-line lg:pl-6`}
              >
                <HostQueue
                  queue={liveQueue}
                  tables={snapshot.plan_sali?.stoliki || []}
                  pick={pick}
                  setPick={setPick}
                  actions={actions}
                  feedback={rowFeedback}
                  canViewContacts={canViewContacts}
                  canViewSensitive={canViewSensitive}
                  readOnly={readOnly}
                  day={data}
                  now={clockNow}
                  onSeat={posadz}
                  onPhase={changePhase}
                  onRetry={retryRowAction}
                />
              </div>
            </div>

            <div
              className={`${mobileView === 'timeline' ? 'block' : 'hidden'} mt-6 border-t border-line pt-6 lg:block`}
            >
              <HostTimeline timeline={snapshot.os_czasu} canViewContacts={canViewContacts} />
            </div>
          </div>
        ) : null}
      </div>
    </Card>
  )
}

function Metric({ value, label, accent = false }) {
  return (
    <span className="inline-flex items-baseline gap-1.5 whitespace-nowrap">
      <strong className={`font-display text-lg font-semibold tabular-nums ${accent ? 'text-mint' : 'text-ink'}`}>{value}</strong>
      <span className="text-xs text-muted">{label}</span>
    </span>
  )
}

function HostQueue({
  queue,
  tables,
  pick,
  setPick,
  actions,
  feedback,
  canViewContacts,
  canViewSensitive,
  readOnly,
  day,
  now,
  onSeat,
  onPhase,
  onRetry,
}) {
  const tableName = (id) => tables.find((table) => table.id === id)?.nazwa || `#${id}`
  const tableLabel = (reservation) => {
    const ids = tableIdsFor(reservation)
    return ids.length ? ids.map(tableName).join(' + ') : null
  }
  const availableTables = tables.filter((table) => table.aktywny && table.aktywny_w_planie !== false)
  const empty = !(queue?.nadchodzace?.length || queue?.na_sali?.length || queue?.zakonczone?.length || queue?.waitlista?.length)

  return (
    <section aria-labelledby="host-queue-title" className="min-w-0 lg:max-h-[46rem] lg:overflow-y-auto lg:pr-1">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h3 id="host-queue-title" className="text-base font-semibold text-ink">Goście</h3>
          <p className="mt-0.5 text-xs text-muted">Najbliższe działania w kolejności serwisu</p>
        </div>
        {readOnly ? <span className="rounded-full border border-lemon/25 bg-lemon/8 px-2.5 py-1 text-[0.68rem] font-semibold text-lemon">Tylko podgląd</span> : null}
      </div>
      <p id="host-readonly-actions" className="sr-only">Brak aktualnego połączenia — akcje są dostępne tylko w trybie online.</p>

      {empty ? (
        <div className="mt-4 rounded-xl border border-dashed border-line px-4 py-10 text-center">
          <p className="text-sm font-semibold text-ink">Spokojny serwis</p>
          <p className="mt-1 text-xs text-muted">Brak rezerwacji i oczekujących dla tego dnia.</p>
        </div>
      ) : null}

      <QueueSection title="Przy wejściu" count={queue?.nadchodzace?.length || 0}>
        {(queue?.nadchodzace || []).length === 0 ? <EmptyRow>Na razie nikt nie czeka.</EmptyRow> : null}
        {(queue?.nadchodzace || []).map((reservation) => (
          <div key={reservation.id} className="border-b border-line py-3 last:border-b-0">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-base font-semibold tabular-nums text-ink">{reservation.godz_od || '—'}</span>
                  {reservation.faza_hosta === 'przybyl' ? <span className="rounded-full bg-lemon/12 px-2 py-0.5 text-[0.68rem] font-semibold text-lemon">Przybyli</span> : null}
                </div>
                <p className="mt-0.5 truncate text-sm font-semibold text-ink">{canViewContacts ? reservation.nazwisko : 'Gość'}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {reservation.liczba_osob ? `${reservation.liczba_osob} os.` : 'Liczba osób nieznana'}
                  {tableLabel(reservation) ? ` · ${tableLabel(reservation)}` : ' · bez stołu'}
                </p>
              </div>
              <DaneWrazliwe guest={reservation.gosc} visible={canViewSensitive} compact />
            </div>
            <div className="mt-3 flex items-center gap-2">
              <label className="sr-only" htmlFor={`host-table-${reservation.id}`}>Stół dla {canViewContacts ? reservation.nazwisko : 'gościa'}</label>
              <select
                id={`host-table-${reservation.id}`}
                value={pick[reservation.id] || ''}
                disabled={Boolean(actions[reservation.id]) || readOnly}
                aria-describedby={readOnly ? 'host-readonly-actions' : undefined}
                onChange={(event) => setPick((current) => ({ ...current, [reservation.id]: event.target.value }))}
                className={`${fld} min-h-11 min-w-0 flex-1`}
              >
                <option value="">Dobierz automatycznie</option>
                {availableTables.map((table) => <option key={table.id} value={table.id}>{table.nazwa} · {table.pojemnosc} os.</option>)}
              </select>
              <Button
                variant={reservation.faza_hosta === 'przybyl' ? 'primary' : 'ghost'}
                size="sm"
                onClick={() => onSeat(reservation)}
                disabled={Boolean(actions[reservation.id]) || readOnly}
                loading={actions[reservation.id] === 'seat'}
                loadingLabel="Sadzam…"
                aria-describedby={readOnly ? 'host-readonly-actions' : undefined}
                className="shrink-0"
              >
                <Icon name="check" className="h-4 w-4" /> Posadź
              </Button>
            </div>
            <InlineFeedback value={feedback[reservation.id]} onRetry={() => onRetry(reservation, feedback[reservation.id]?.retry)} disabled={readOnly || Boolean(actions[reservation.id])} />
          </div>
        ))}
      </QueueSection>

      <QueueSection title="Na sali" count={queue?.na_sali?.length || 0} accent>
        {(queue?.na_sali || []).length === 0 ? <EmptyRow>Sala jest pusta.</EmptyRow> : null}
        {(queue?.na_sali || []).map((reservation) => {
          const meta = FAZA_META[reservation.faza_hosta] || FAZA_META.posadzony
          const timing = visitTiming(reservation, day, now)
          return (
            <div key={reservation.id} className="border-b border-line py-3 last:border-b-0">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">{canViewContacts ? reservation.nazwisko : 'Gość'}</p>
                  <p className="mt-0.5 text-xs text-muted">{tableLabel(reservation) || 'Bez stołu'}{reservation.liczba_osob ? ` · ${reservation.liczba_osob} os.` : ''}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className={`text-xs font-semibold tabular-nums ${timing.className}`}>{timing.text}</p>
                  <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[0.68rem] font-semibold ${meta.className}`}>{meta.label}</span>
                </div>
              </div>
              <DaneWrazliwe guest={reservation.gosc} visible={canViewSensitive} />
              <div className="mt-3 flex flex-wrap gap-2">
                {reservation.faza_hosta === 'posadzony' ? <PhaseButton disabled={Boolean(actions[reservation.id]) || readOnly} describedBy={readOnly ? 'host-readonly-actions' : undefined} onClick={() => onPhase(reservation, 'rachunek')} icon="clipboard">Rachunek</PhaseButton> : null}
                {['posadzony', 'rachunek'].includes(reservation.faza_hosta) ? <PhaseButton disabled={Boolean(actions[reservation.id]) || readOnly} describedBy={readOnly ? 'host-readonly-actions' : undefined} onClick={() => onPhase(reservation, 'oplacony')} icon="check">Opłacony</PhaseButton> : null}
                <PhaseButton disabled={Boolean(actions[reservation.id]) || readOnly} describedBy={readOnly ? 'host-readonly-actions' : undefined} onClick={() => onPhase(reservation, 'wyszedl')} icon="close" quiet>Wyszedł</PhaseButton>
              </div>
              <InlineFeedback value={feedback[reservation.id]} onRetry={() => onRetry(reservation, feedback[reservation.id]?.retry)} disabled={readOnly || Boolean(actions[reservation.id])} />
            </div>
          )
        })}
      </QueueSection>

      {(queue?.waitlista || []).length ? (
        <QueueSection title="Lista oczekujących" count={queue.waitlista.length}>
          {queue.waitlista.map((entry) => (
            <div key={entry.id} className="flex min-h-11 items-center justify-between gap-3 border-b border-line py-2 last:border-b-0">
              <span className="truncate text-sm font-medium text-ink">{canViewContacts ? entry.nazwisko : 'Gość'}</span>
              <span className="shrink-0 text-xs text-muted">{[entry.godz_od, entry.liczba_osob ? `${entry.liczba_osob} os.` : null].filter(Boolean).join(' · ')}</span>
            </div>
          ))}
        </QueueSection>
      ) : null}

      {(queue?.zakonczone || []).length ? (
        <QueueSection title="Zakończeni" count={queue.zakonczone.length} quiet>
          {queue.zakonczone.map((reservation) => (
            <div key={reservation.id} className="flex min-h-11 items-center justify-between gap-3 border-b border-line py-2 text-sm last:border-b-0">
              <span className="truncate text-muted"><span className="font-medium text-ink/80">{canViewContacts ? reservation.nazwisko : 'Gość'}</span>{tableLabel(reservation) ? ` · ${tableLabel(reservation)}` : ''}</span>
              <span className="shrink-0 text-[0.68rem] text-muted">{reservation.status === 'no_show' ? 'nie przyszli' : 'zakończona'}</span>
            </div>
          ))}
        </QueueSection>
      ) : null}
    </section>
  )
}

function QueueSection({ title, count, accent = false, quiet = false, children }) {
  return (
    <div className="mt-5">
      <div className="flex items-center gap-2 border-b border-line pb-2">
        <h4 className={`text-xs font-semibold ${quiet ? 'text-muted' : 'text-ink'}`}>{title}</h4>
        <span className={`rounded-full px-2 py-0.5 text-[0.68rem] font-semibold tabular-nums ${accent ? 'bg-mint/12 text-mint' : 'bg-white/[0.06] text-muted'}`}>{count}</span>
      </div>
      <div>{children}</div>
    </div>
  )
}

function EmptyRow({ children }) {
  return <p className="py-6 text-center text-xs text-muted">{children}</p>
}

function PhaseButton({ onClick, icon, children, quiet = false, disabled, describedBy }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-describedby={describedBy}
      className={`inline-flex min-h-11 items-center gap-1.5 rounded-xl border border-line px-3 text-xs font-semibold transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${quiet ? 'text-muted hover:border-danger/35 hover:text-danger' : 'text-muted hover:bg-white/[0.05] hover:text-ink'}`}
    >
      <Icon name={icon} className="h-3.5 w-3.5" /> {children}
    </button>
  )
}

function InlineFeedback({ value, onRetry, disabled }) {
  if (!value) return null
  return (
    <div className={`mt-2 flex min-h-6 flex-wrap items-center gap-2 text-xs ${value.type === 'error' ? 'text-danger' : 'text-success'}`} role={value.type === 'error' ? 'alert' : 'status'} aria-live="polite">
      <span>{value.message}</span>
      {value.type === 'error' && value.retry ? (
        <button type="button" onClick={onRetry} disabled={disabled} className="min-h-8 rounded-lg px-2 font-semibold underline decoration-current/40 underline-offset-2 disabled:opacity-50">Ponów</button>
      ) : null}
    </div>
  )
}

function DaneWrazliwe({ guest, visible, compact = false }) {
  if (!visible || !guest || (!guest.ma_alergie && !guest.alergie)) return null
  return (
    <div className={`${compact ? 'max-w-[8rem]' : 'mt-2'} flex items-start gap-1.5 rounded-lg bg-danger/10 px-2 py-1.5 text-xs font-medium text-danger`}>
      <Icon name="warning" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span className="line-clamp-2">{guest.alergie ? `Alergie: ${guest.alergie}` : 'Alergie — sprawdź profil'}</span>
    </div>
  )
}

function HostSkeleton() {
  return (
    <div className="mt-5 animate-pulse lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(22rem,0.65fr)]" aria-label="Ładowanie serwisu">
      <div className="lg:pr-6">
        <div className="h-5 w-28 rounded bg-white/[0.07]" />
        <div className="mt-4 aspect-[4/3] min-h-64 rounded-2xl border border-line bg-white/[0.025]" />
      </div>
      <div className="mt-6 lg:mt-0 lg:border-l lg:border-line lg:pl-6">
        <div className="h-5 w-24 rounded bg-white/[0.07]" />
        {[1, 2, 3].map((key) => <div key={key} className="mt-4 h-24 rounded-xl border border-line bg-white/[0.025]" />)}
      </div>
    </div>
  )
}

export { patchSnapshotReservation, visitTiming }
