import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { PillSwitch } from '../ui/PillSwitch'
import { Icon } from '../../lib/icons'
import { api, nowyKluczIdempotencji } from '../../lib/api'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { useAuth } from '../../context/AuthContext'
import { warsawDateISO } from '../../lib/date'
import { shiftDateIso } from '../../lib/reservationRoute'
import { readHostSnapshotCache, writeHostSnapshotCache } from '../../lib/hostSnapshotCache'
import HostFloorPlan from './HostFloorPlan'
import HostTimeline from './HostTimeline'
import ReservationCommunicationPanel from './ReservationCommunicationPanel'
import ReservationCommunicationStatus from './ReservationCommunicationStatus'
import ReservationOverridePanel from './ReservationOverridePanel'

const POLL_INTERVAL_MS = 30000
const CLOCK_INTERVAL_MS = 30000
const HOST_ON_FLOOR = new Set(['posadzony', 'rachunek', 'oplacony'])
const HOST_FINISHED = new Set(['wyszedl'])
const RESERVATION_FINISHED = new Set(['odbyla', 'no_show'])
const WAITLIST_ACTIVE = new Set(['oczekuje', 'zaoferowano'])
const WAITLIST_TERMINAL = new Set(['zaakceptowano', 'wygasla', 'anulowano'])
const WAITLIST_STATUS_ORDER = { zaoferowano: 0, oczekuje: 1 }
const WAITLIST_TERMINAL_LABELS = {
  zaakceptowano: 'Oferta zaakceptowana',
  wygasla: 'Oferta wygasła',
  anulowano: 'Oczekiwanie anulowane',
}
const OFFER_RESELECT_CODES = new Set([
  'TABLE_CONFLICT',
  'INVALID_TABLE_COMBINATION',
  'WAITLIST_OFFER_PLAN_CHANGED',
])
const WAITLIST_DELIVERY_RECONCILIATION_CODE = 'WAITLIST_DELIVERY_RECONCILIATION_REQUIRED'
const WAITLIST_DELIVERY_RECONCILIATION_MESSAGE = 'Nie znamy wyniku poprzedniej wysyłki. Przed nową ofertą wybierz „Komunikacja” przy tym wpisie i uzgodnij poprzednią wysyłkę.'
const OFFER_CLOCK_INTERVAL_MS = 1000
const dzisISO = () => warsawDateISO()
const fld = 'rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink outline-none transition focus:border-mint/60 focus:ring-2 focus:ring-mint/20'
const emptyOverrideDraft = () => ({ powod: '', notatka: '' })

const isLimitOverrideRequired = (error) => (
  ['PACING_RESERVATION_LIMIT', 'PACING_COVERS_LIMIT'].includes(error?.code)
  || error?.availability?.decision === 'override_required'
  || error?.availability?.can_override === true
  || error?.availability?.violations?.some((violation) => violation.overrideable_by_operator)
)

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

const waitlistTableIds = (entry) => [
  entry?.hold_stolik_id,
  ...(entry?.hold_stoliki_dodatkowe || []),
].map(Number).filter((id) => Number.isFinite(id) && id > 0)

const parseUtcTimestamp = (value) => {
  if (!value) return null
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  const parsed = Date.parse(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

const sortOperationalWaitlist = (entries) => [...entries].sort((first, second) => {
  const status = (WAITLIST_STATUS_ORDER[first.status] ?? 9) - (WAITLIST_STATUS_ORDER[second.status] ?? 9)
  if (status) return status
  if (first.status === 'zaoferowano') {
    const deadline = (parseUtcTimestamp(first.hold_do) ?? Number.MAX_SAFE_INTEGER)
      - (parseUtcTimestamp(second.hold_do) ?? Number.MAX_SAFE_INTEGER)
    if (deadline) return deadline
  }
  const priority = Number(second.priorytet || 0) - Number(first.priorytet || 0)
  if (priority) return priority
  const created = (parseUtcTimestamp(first.utworzono_at) ?? Number.MAX_SAFE_INTEGER)
    - (parseUtcTimestamp(second.utworzono_at) ?? Number.MAX_SAFE_INTEGER)
  return created || first.id - second.id
})

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

const restoredTableStatus = (table) => {
  if (!table.aktywny || table.aktywny_w_planie === false) return 'nieaktywny'
  if (table.live?.zajete) return 'zajety_live'
  const reservations = (table.rezerwacje || []).filter((entry) => (
    entry.status !== 'odwolana' && !RESERVATION_FINISHED.has(entry.status)
  ))
  if (reservations.some((entry) => entry.status === 'potwierdzona')) return 'potwierdzony'
  if (reservations.length) return 'zarezerwowany'
  return 'bez_rezerwacji'
}

function patchSnapshotWaitlist(snapshot, response) {
  const entry = response?.wpis || response
  if (!snapshot?.kolejka || !entry?.id) return snapshot
  const previous = (snapshot.kolejka.waitlista || []).find((item) => item.id === entry.id)
  const waitlista = (snapshot.kolejka.waitlista || []).filter((item) => item.id !== entry.id)
  if (WAITLIST_ACTIVE.has(entry.status)) waitlista.push(entry)
  const nextWaitlist = sortOperationalWaitlist(waitlista)
  const communicationInbox = (snapshot.kolejka.komunikacja_waitlist || [])
    .filter((item) => item.id !== entry.id)
  if (
    WAITLIST_TERMINAL.has(entry.status)
    && entry.communication_summary?.attention_required === true
  ) {
    communicationInbox.push({
      id: entry.id,
      nazwisko: entry.nazwisko || 'Gość',
      status: entry.status,
      communication_summary: entry.communication_summary,
    })
  }
  const nextQueue = {
    ...snapshot.kolejka,
    waitlista: nextWaitlist,
    komunikacja_waitlist: communicationInbox,
  }
  nextQueue.podsumowanie = queueSummary(nextQueue)

  const oldTableIds = new Set(waitlistTableIds(previous))
  const offeredByTable = new Map()
  for (const item of nextWaitlist) {
    if (item.status !== 'zaoferowano') continue
    for (const tableId of waitlistTableIds(item)) offeredByTable.set(tableId, item)
  }
  const nextFloor = snapshot.plan_sali ? {
    ...snapshot.plan_sali,
    stoliki: (snapshot.plan_sali.stoliki || []).map((table) => {
      const offer = offeredByTable.get(table.id)
      if (offer) {
        return {
          ...table,
          status: 'wstrzymany',
          waitlist_offer: {
            waitlist_id: offer.id,
            hold_do: offer.hold_do,
            liczba_osob: offer.liczba_osob,
          },
        }
      }
      if (oldTableIds.has(table.id) || table.waitlist_offer?.waitlist_id === entry.id) {
        const { waitlist_offer: _removed, ...rest } = table
        return { ...rest, status: restoredTableStatus(table) }
      }
      return table
    }),
  } : snapshot.plan_sali

  const remainingOccupancies = (snapshot.os_czasu?.zajetosci || []).filter((item) => item.waitlist_id !== entry.id)
  const offerOccupancies = entry.status === 'zaoferowano'
    ? waitlistTableIds(entry).map((tableId) => ({
        typ: 'oferta',
        waitlist_id: entry.id,
        rezerwacja_id: null,
        stolik_id: tableId,
        godz_od: entry.hold_godz_od || entry.godz_od,
        godz_do: entry.hold_godz_do,
        hold_do: entry.hold_do,
        nazwisko: entry.nazwisko || 'Gość',
        liczba_osob: entry.liczba_osob,
      })).filter((item) => item.godz_od && item.godz_do)
    : []
  let nextSnapshot = {
    ...snapshot,
    kolejka: nextQueue,
    plan_sali: nextFloor,
    os_czasu: snapshot.os_czasu
      ? { ...snapshot.os_czasu, zajetosci: [...remainingOccupancies, ...offerOccupancies] }
      : snapshot.os_czasu,
  }
  if (response?.rezerwacja) nextSnapshot = patchSnapshotReservation(nextSnapshot, response.rezerwacja)
  return nextSnapshot
}

const tableIdsFromCandidate = (candidate) => {
  const raw = candidate?.table_ids
    || candidate?.stoliki
    || candidate?.tables?.map((table) => table?.id)
    || []
  return [...new Set(raw.map(Number).filter((id) => Number.isFinite(id) && id > 0))]
}

const normalizeSuggestion = (result) => {
  const rawCandidates = result?.candidates || result?.kandydaci || []
  const selectedIds = tableIdsFromCandidate(
    result?.selected || result?.allocation || rawCandidates[0],
  )
  const candidates = [
    ...(selectedIds.length ? [{ ...(result?.selected || result?.allocation || {}), table_ids: selectedIds }] : []),
    ...rawCandidates,
  ].reduce((output, candidate) => {
    const tableIds = tableIdsFromCandidate(candidate)
    const key = tableIds.join(':')
    if (!key || output.some((item) => item.key === key)) return output
    output.push({ key, tableIds, source: candidate })
    return output
  }, [])
  return { candidates, selectedIds: selectedIds.length ? selectedIds : candidates[0]?.tableIds || [] }
}

const formatOfferClock = (timestamp) => new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit',
}).format(new Date(timestamp))

const offerTiming = (entry, serverNowMs, stale = false) => {
  const deadline = parseUtcTimestamp(entry?.hold_do)
  if (deadline == null) return { expired: true, text: 'Brak terminu oferty', absolute: null }
  const absolute = formatOfferClock(deadline)
  if (stale) {
    return {
      expired: deadline <= serverNowMs,
      text: deadline <= serverNowMs
        ? `Termin oferty minął · była ważna do ${absolute}`
        : `Według zapisanych danych ważna do ${absolute}`,
      absolute,
    }
  }
  const remainingMs = deadline - serverNowMs
  if (remainingMs <= 0) return { expired: true, text: `Oferta wygasła · do ${absolute}`, absolute }
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000))
  const text = totalSeconds <= 120
    ? `jeszcze ${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`
    : `jeszcze ${Math.ceil(totalSeconds / 60)} min`
  return { expired: false, text: `${text} · do ${absolute}`, absolute, urgent: totalSeconds <= 300, danger: totalSeconds <= 60 }
}

const offerSuccessMessage = (response, fallbackNow) => {
  const deadline = parseUtcTimestamp(response?.wpis?.hold_do)
  const until = formatOfferClock(deadline ?? fallbackNow)
  const summary = response?.wpis?.communication_summary
  const messageStates = new Set((response?.messages || []).map((message) => message?.state).filter(Boolean))
  if (response?.queued) {
    return `Oferta aktywna. Powiadomienie jest w kolejce. Stoliki są trzymane do ${until}.`
  }
  if (summary?.state === 'sent' || messageStates.has('sent')) {
    return `Oferta aktywna. Powiadomienie zostało dostarczone. Stoliki są trzymane do ${until}.`
  }
  const needsAttention = summary?.attention_required
    || Number(summary?.attention_count || 0) > 0
    || ['failed', 'uncertain'].includes(summary?.state)
    || messageStates.has('failed')
    || messageStates.has('uncertain')
  if (needsAttention) {
    return `Oferta aktywna do ${until}. Sprawdź komunikację lub poinformuj gościa na miejscu.`
  }
  return `Oferta aktywna do ${until}. Poinformuj gościa na miejscu.`
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

const warsawClockLabel = (nowMs) => new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
}).format(new Date(nowMs))

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
  const {
    user,
    can,
    isAdmin,
    workstationSession,
    reauthorizeWorkstation,
  } = useAuth()
  const canViewSensitive = isAdmin || can('rezerwacje.dane_wrazliwe')
  const canViewContacts = isAdmin || can('rezerwacje.dane_kontaktowe')
  const canOverrideLimits = isAdmin || can('rezerwacje.nadpisuj_limity')
  const requiresWorkstationReauth = Boolean(workstationSession?.active)
  const dateControlled = controlledDate !== undefined
  const [localDate, setLocalDate] = useState(dzisISO())
  const data = dateControlled ? controlledDate : localDate
  const dataRef = useRef(data)
  const [snapshot, setSnapshot] = useState(null)
  const snapshotRef = useRef(null)
  const snapshotServerTimeRef = useRef(Date.now())
  const snapshotReceivedAtRef = useRef(Date.now())
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
  const [waitDrafts, setWaitDrafts] = useState({})
  const [waitActions, setWaitActions] = useState({})
  const [waitFeedback, setWaitFeedback] = useState({})
  const [waitOverrides, setWaitOverrides] = useState({})
  const [waitOverrideDrafts, setWaitOverrideDrafts] = useState({})
  const [waitConfirmation, setWaitConfirmation] = useState(null)
  const [clockNow, setClockNow] = useState(Date.now())
  const requestId = useRef(0)
  const loadControllerRef = useRef(null)
  const hasDataRef = useRef(false)
  const mutationGenerationRef = useRef(0)
  const mutationControllersRef = useRef(new Set())
  const waitIdempotencyRef = useRef(new Map())
  const expiredOfferRefreshRef = useRef(new Set())

  const updateWaitlistCommunicationSummary = useCallback((summary, owner) => {
    if (owner?.type !== 'waitlist') return
    const current = snapshotRef.current
    const entry = (current?.kolejka?.waitlista || []).find((item) => item.id === owner.id)
    let patched
    if (entry) {
      patched = patchSnapshotWaitlist(current, { ...entry, communication_summary: summary })
    } else {
      const inbox = current?.kolejka?.komunikacja_waitlist || []
      const terminalEntry = inbox.find((item) => item.id === owner.id)
      if (!terminalEntry) return
      const nextInbox = inbox.filter((item) => item.id !== owner.id)
      if (summary?.attention_required === true) {
        nextInbox.push({ ...terminalEntry, communication_summary: summary })
      }
      patched = {
        ...current,
        kolejka: {
          ...current.kolejka,
          komunikacja_waitlist: nextInbox,
        },
      }
    }
    snapshotRef.current = patched
    setSnapshot(patched)
    const now = Date.now()
    const serverNow = snapshotServerTimeRef.current
      + Math.max(0, now - snapshotReceivedAtRef.current)
    writeHostSnapshotCache(user, patched, { serverNow })
  }, [user])

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
    const receivedAt = Date.now()
    const cacheClock = fromCache ? next.__hostCacheClock : null
    const cachedAt = Number(cacheClock?.cachedAt)
    const elapsedSinceCache = Number.isFinite(cachedAt) ? Math.max(0, receivedAt - cachedAt) : 0
    const serverAtCache = parseUtcTimestamp(cacheClock?.serverTimeAtCache)
      ?? parseUtcTimestamp(next.generated_at)
      ?? receivedAt
    const previousServerEstimate = hasDataRef.current
      ? snapshotServerTimeRef.current + Math.max(0, receivedAt - snapshotReceivedAtRef.current)
      : null
    snapshotServerTimeRef.current = previousServerEstimate == null
      ? serverAtCache + elapsedSinceCache
      : Math.max(serverAtCache + elapsedSinceCache, previousServerEstimate)
    snapshotReceivedAtRef.current = receivedAt
    snapshotRef.current = next
    hasDataRef.current = true
    setSnapshot(next)
    setCached(fromCache)
    setClockNow(receivedAt)
    if (persist) writeHostSnapshotCache(user, next, { serverNow: snapshotServerTimeRef.current })
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
      setWaitDrafts({})
      setWaitActions({})
      setWaitFeedback({})
      setWaitOverrides({})
      setWaitOverrideDrafts({})
      setWaitConfirmation(null)
      waitIdempotencyRef.current.clear()
      expiredOfferRefreshRef.current.clear()
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
    cancelMutationContinuations()
    hasDataRef.current = false
    snapshotRef.current = null
    setSnapshot(null)
    setCached(false)
    setLoading(true)
    setLoadError(null)
    setRefreshError(null)
    setRefreshing(false)
    setPick({})
    setActions({})
    setRowFeedback({})
    setWaitDrafts({})
    setWaitActions({})
    setWaitFeedback({})
    setWaitOverrides({})
    setWaitOverrideDrafts({})
    setWaitConfirmation(null)
    waitIdempotencyRef.current.clear()
    expiredOfferRefreshRef.current.clear()
    if (active && isVisible()) void load({ day: data })
  }, [active, cancelMutationContinuations, cancelReadRequests, data, load])

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
    let timeoutId = null
    const schedule = () => {
      if (timeoutId != null) window.clearTimeout(timeoutId)
      const serverAtSchedule = snapshotServerTimeRef.current
        + Math.max(0, Date.now() - snapshotReceivedAtRef.current)
      const nearExpiry = (snapshot.kolejka?.waitlista || []).some((entry) => {
        if (entry.status !== 'zaoferowano') return false
        const remaining = (parseUtcTimestamp(entry.hold_do) ?? Number.MAX_SAFE_INTEGER) - serverAtSchedule
        return remaining > 0 && remaining <= 2 * 60 * 1000
      })
      timeoutId = window.setTimeout(() => {
        tick()
        schedule()
      }, nearExpiry ? OFFER_CLOCK_INTERVAL_MS : CLOCK_INTERVAL_MS)
    }
    const onVisibilityChange = () => {
      tick()
      schedule()
    }
    schedule()
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      if (timeoutId != null) window.clearTimeout(timeoutId)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [active, snapshot])

  const changeDay = (nextDay) => {
    if (!nextDay || nextDay === data) return
    onDateChange?.(nextDay)
    cancelMutationContinuations()
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
    setActions({})
    setRowFeedback({})
    setWaitDrafts({})
    setWaitActions({})
    setWaitFeedback({})
    setWaitOverrides({})
    setWaitOverrideDrafts({})
    setWaitConfirmation(null)
    waitIdempotencyRef.current.clear()
    expiredOfferRefreshRef.current.clear()
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

  const serverNowEstimate = (clientNow = Date.now()) => (
    snapshotServerTimeRef.current + Math.max(0, clientNow - snapshotReceivedAtRef.current)
  )

  const applyLocalSnapshot = (patched) => {
    if (!patched) return
    const receivedAt = Date.now()
    const estimatedServerNow = serverNowEstimate(receivedAt)
    snapshotRef.current = patched
    snapshotServerTimeRef.current = estimatedServerNow
    snapshotReceivedAtRef.current = receivedAt
    setSnapshot(patched)
    setClockNow(receivedAt)
    writeHostSnapshotCache(user, patched, { serverNow: estimatedServerNow })
  }

  const applyMutationResponse = (response) => {
    const patched = patchSnapshotReservation(snapshotRef.current, response)
    applyLocalSnapshot(patched)
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

  const beginWaitAction = (id, action) => {
    setWaitActions((current) => ({ ...current, [id]: action }))
    setWaitFeedback((current) => ({ ...current, [id]: null }))
    setWaitConfirmation(null)
  }

  const endWaitAction = (id) => setWaitActions((current) => {
    const next = { ...current }
    delete next[id]
    return next
  })

  const handleWaitError = (entry, error, fallback, operationDay, { ambiguousWrite = true } = {}) => {
    if (error?.status == null && ambiguousWrite) {
      setConnection(isOnline() ? 'stale' : 'offline')
      setRefreshError('Nie udało się potwierdzić wyniku ostatniej akcji. Odśwież widok przed kolejnym zapisem.')
      setWaitFeedback((current) => ({
        ...current,
        [entry.id]: {
          type: 'error',
          message: 'Połączenie zostało przerwane. Nie znamy wyniku — odśwież widok przed ponowieniem.',
        },
      }))
      return
    }
    const deliveryReconciliationRequired = error.status === 409
      && error.code === WAITLIST_DELIVERY_RECONCILIATION_CODE
    const staleOffer = error.status === 409 && String(error.code || '').includes('OFFER')
    setWaitFeedback((current) => ({
      ...current,
      [entry.id]: {
        type: staleOffer || deliveryReconciliationRequired ? 'warning' : 'error',
        message: deliveryReconciliationRequired
          ? WAITLIST_DELIVERY_RECONCILIATION_MESSAGE
          : (error?.status == null ? fallback : (error.message || fallback)),
        communicationRequired: deliveryReconciliationRequired,
      },
    }))
    if (staleOffer || deliveryReconciliationRequired) void load({ quiet: true, day: operationDay })
  }

  const previewWaitlistOffer = async (entry) => {
    if (waitActions[entry.id] || readOnly) return
    const operationDay = dataRef.current
    const offerTime = entry.godz_od || warsawClockLabel(serverNowEstimate())
    beginWaitAction(entry.id, 'preview')
    const mutation = startMutation()
    try {
      const result = await api(
        `/host/sugestia-stolika?data=${encodeURIComponent(operationDay)}&godz_od=${encodeURIComponent(offerTime)}&osoby=${Math.max(1, Number(entry.liczba_osob) || 1)}&waitlist_id=${encodeURIComponent(entry.id)}`,
        'GET',
        null,
        { signal: mutation.controller.signal },
      )
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      const suggestion = normalizeSuggestion(result)
      if (!suggestion.selectedIds.length) {
        const error = new Error('Nie znaleziono wolnej konfiguracji dla tej grupy.')
        error.status = 409
        throw error
      }
      setWaitDrafts((current) => ({
        ...current,
        [entry.id]: {
          time: result.godz_od || offerTime,
          end: result.godz_do || result.visit_end || null,
          minutes: current[entry.id]?.minutes || 10,
          candidates: suggestion.candidates,
          selectedIds: suggestion.selectedIds,
        },
      }))
      setWaitFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'success', message: 'Dobieranie zakończone. Sprawdź stoliki i wyślij ofertę.' },
      }))
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      handleWaitError(entry, error, 'Nie udało się dobrać stolików.', operationDay, { ambiguousWrite: false })
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) endWaitAction(entry.id)
    }
  }

  const sendWaitlistOffer = async (entry, nadpisanieLimitow = null, { pin = '' } = {}) => {
    const draft = waitDrafts[entry.id]
    if (waitActions[entry.id] || readOnly || !draft?.selectedIds?.length) return
    const operationDay = dataRef.current
    const overrideFeedback = nadpisanieLimitow ? waitFeedback[entry.id] : null
    const overrideAvailability = waitOverrides[entry.id] || overrideFeedback?.availability || null
    beginWaitAction(entry.id, 'offer')
    cancelReadRequests()
    const mutation = startMutation()
    let reauthFailed = false
    const keyName = `offer:${entry.id}`
    const idempotencyKey = waitIdempotencyRef.current.get(keyName)
      || nowyKluczIdempotencji('waitlist-offer')
    waitIdempotencyRef.current.set(keyName, idempotencyKey)
    try {
      let reauthGrant = null
      if (nadpisanieLimitow && requiresWorkstationReauth) {
        try {
          const authorization = await reauthorizeWorkstation({
            pin,
            scope: 'reservation_override',
            signal: mutation.controller.signal,
          })
          reauthGrant = authorization?.grant || null
          if (!reauthGrant) {
            const error = new Error('Nie udało się potwierdzić operatora. Wpisz PIN ponownie.')
            error.code = 'WORKSTATION_REAUTH_REQUIRED'
            throw error
          }
        } catch (error) {
          reauthFailed = true
          throw error
        }
      }
      const response = await api(`/lista-oczekujacych/${entry.id}/oferta`, 'POST', {
        stoliki: draft.selectedIds,
        godz_od: draft.time,
        minuty: Number(draft.minutes) || 10,
        expected_offer_version: Number(entry.offer_version) || 0,
        ...(nadpisanieLimitow ? {
          przekrocz_limity: true,
          nadpisanie_limitow: nadpisanieLimitow,
        } : {}),
      }, {
        signal: mutation.controller.signal,
        headers: {
          'Idempotency-Key': idempotencyKey,
          ...(reauthGrant ? { 'X-Lokalo-Workstation-Reauth': reauthGrant } : {}),
        },
      })
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      applyLocalSnapshot(patchSnapshotWaitlist(snapshotRef.current, response))
      waitIdempotencyRef.current.delete(keyName)
      setWaitOverrides((current) => ({ ...current, [entry.id]: null }))
      setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: emptyOverrideDraft() }))
      setWaitDrafts((current) => {
        const next = { ...current }
        delete next[entry.id]
        return next
      })
      setWaitFeedback((current) => ({
        ...current,
        [entry.id]: {
          type: 'success',
          message: offerSuccessMessage(response, serverNowEstimate()),
        },
      }))
      void load({ quiet: true, day: operationDay })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      if (error?.status != null) waitIdempotencyRef.current.delete(keyName)
      const reauthRequired = requiresWorkstationReauth
        && Boolean(nadpisanieLimitow)
        && (
          reauthFailed
          || error?.status === 428
          || String(error?.code || '').startsWith('WORKSTATION_REAUTH')
        )
      if (reauthRequired) {
        setWaitFeedback((current) => ({
          ...current,
          [entry.id]: {
            type: 'warning',
            message: overrideFeedback?.message || 'Ta oferta przekracza ustawiony limit.',
            canOverride: true,
            availability: overrideAvailability || error.availability || null,
            reauthError: error.message || 'Nie udało się potwierdzić PIN-u. Spróbuj ponownie.',
            reauthRetryAfter: Math.max(0, Number(error.retryAfter) || 0),
          },
        }))
        return
      }
      const overrideRequired = isLimitOverrideRequired(error)
      if (overrideRequired && canOverrideLimits) {
        const availability = error.availability || { decision: 'override_required', violations: [] }
        setWaitOverrides((current) => ({ ...current, [entry.id]: availability }))
        setWaitOverrideDrafts((current) => ({
          ...current,
          [entry.id]: current[entry.id] || emptyOverrideDraft(),
        }))
        setWaitFeedback((current) => ({
          ...current,
          [entry.id]: {
            type: 'warning',
            message: error.message || 'Ta oferta przekracza ustawiony limit.',
            canOverride: true,
            availability,
          },
        }))
        return
      }
      if (error?.status === 409 && OFFER_RESELECT_CODES.has(error.code)) {
        setWaitDrafts((current) => {
          const next = { ...current }
          delete next[entry.id]
          return next
        })
        setWaitOverrides((current) => ({ ...current, [entry.id]: null }))
        setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: emptyOverrideDraft() }))
        setWaitFeedback((current) => ({
          ...current,
          [entry.id]: {
            type: 'warning',
            message: 'Wybrana konfiguracja nie jest już dostępna. Dobierz stoliki ponownie.',
          },
        }))
        void load({ quiet: true, day: operationDay })
      } else {
        handleWaitError(entry, error, 'Nie udało się wysłać oferty.', operationDay)
      }
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) endWaitAction(entry.id)
    }
  }

  const acceptWaitlistOffer = async (entry) => {
    if (waitActions[entry.id] || readOnly) return
    const operationDay = dataRef.current
    beginWaitAction(entry.id, 'accept')
    cancelReadRequests()
    const mutation = startMutation()
    const keyName = `accept:${entry.id}`
    const idempotencyKey = waitIdempotencyRef.current.get(keyName)
      || nowyKluczIdempotencji('waitlist-accept')
    waitIdempotencyRef.current.set(keyName, idempotencyKey)
    try {
      const response = await api(`/lista-oczekujacych/${entry.id}/zaakceptuj`, 'POST', {
        tryb: 'rezerwacja',
        offer_version: Number(entry.offer_version) || 0,
      }, {
        signal: mutation.controller.signal,
        headers: { 'Idempotency-Key': idempotencyKey },
      })
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      applyLocalSnapshot(patchSnapshotWaitlist(snapshotRef.current, response))
      waitIdempotencyRef.current.delete(keyName)
      if (response.rezerwacja?.id) {
        setRowFeedback((current) => ({
          ...current,
          [response.rezerwacja.id]: { type: 'success', message: 'Gość przyjął ofertę. Rezerwacja jest gotowa do posadzenia.' },
        }))
        window.requestAnimationFrame(() => document.getElementById(`host-seat-${response.rezerwacja.id}`)?.focus())
      }
      void load({ quiet: true, day: operationDay })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      if (error?.status != null) waitIdempotencyRef.current.delete(keyName)
      handleWaitError(entry, error, 'Nie udało się przyjąć oferty.', operationDay)
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) endWaitAction(entry.id)
    }
  }

  const withdrawWaitlistOffer = async (entry) => {
    if (waitActions[entry.id] || readOnly) return
    const operationDay = dataRef.current
    beginWaitAction(entry.id, 'withdraw')
    cancelReadRequests()
    const mutation = startMutation()
    try {
      const response = await api(`/lista-oczekujacych/${entry.id}/wycofaj-oferte`, 'POST', {
        offer_version: Number(entry.offer_version) || 0,
      }, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      applyLocalSnapshot(patchSnapshotWaitlist(snapshotRef.current, response))
      setWaitFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'success', message: 'Oferta wycofana. Stoliki wróciły do puli.' },
      }))
      void load({ quiet: true, day: operationDay })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      handleWaitError(entry, error, 'Nie udało się wycofać oferty.', operationDay)
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) endWaitAction(entry.id)
    }
  }

  const cancelWaitlistEntry = async (entry) => {
    if (waitActions[entry.id] || readOnly) return
    const operationDay = dataRef.current
    beginWaitAction(entry.id, 'cancel')
    cancelReadRequests()
    const mutation = startMutation()
    try {
      const response = await api(`/lista-oczekujacych/${entry.id}/anuluj`, 'POST', {
        expected_offer_version: Number(entry.offer_version) || 0,
      }, {
        signal: mutation.controller.signal,
      })
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      applyLocalSnapshot(patchSnapshotWaitlist(snapshotRef.current, response))
      void load({ quiet: true, day: operationDay })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      handleWaitError(entry, error, 'Nie udało się anulować oczekiwania.', operationDay)
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) endWaitAction(entry.id)
    }
  }

  const toggleWaitlistPriority = async (entry) => {
    if (waitActions[entry.id] || readOnly) return
    const operationDay = dataRef.current
    beginWaitAction(entry.id, 'priority')
    cancelReadRequests()
    const mutation = startMutation()
    const priority = Number(entry.priorytet) === 1 ? 0 : 1
    try {
      const response = await api(`/lista-oczekujacych/${entry.id}/priorytet`, 'POST', {
        priorytet: priority,
        expected_offer_version: Number(entry.offer_version) || 0,
      }, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation) || dataRef.current !== operationDay) return
      applyLocalSnapshot(patchSnapshotWaitlist(snapshotRef.current, response))
      setWaitFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'success', message: priority ? 'Wpis ma teraz priorytet.' : 'Przywrócono zwykłą kolejność.' },
      }))
      void load({ quiet: true, day: operationDay })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError' || dataRef.current !== operationDay) return
      handleWaitError(entry, error, 'Nie udało się zmienić priorytetu.', operationDay)
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) endWaitAction(entry.id)
    }
  }

  const liveQueue = useMemo(() => {
    if (!snapshot?.kolejka) return null
    const elapsed = Math.max(0, Math.floor((clockNow - snapshotReceivedAtRef.current) / 60000))
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
  const serverNow = snapshotServerTimeRef.current + Math.max(0, clockNow - snapshotReceivedAtRef.current)

  useEffect(() => {
    if (!active || !liveQueue?.waitlista?.length) return
    const expired = liveQueue.waitlista.find((entry) => {
      if (entry.status !== 'zaoferowano') return false
      const deadline = parseUtcTimestamp(entry.hold_do)
      return deadline != null && deadline <= serverNow
    })
    if (!expired) return
    const key = `${expired.id}:${expired.offer_version || 0}`
    applyLocalSnapshot(patchSnapshotWaitlist(snapshotRef.current, {
      ...expired,
      status: 'wygasla',
      wygasla_at: new Date(serverNow).toISOString(),
    }))
    if (!expiredOfferRefreshRef.current.has(key)) {
      expiredOfferRefreshRef.current.add(key)
      if (isOnline()) void load({ quiet: true, day: dataRef.current })
    }
  }, [active, liveQueue, load, serverNow])

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
              <Metric value={summary.waitlista ?? liveQueue?.waitlista?.length ?? 0} label="na waitliście" />
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
                  waitDrafts={waitDrafts}
                  setWaitDrafts={setWaitDrafts}
                  waitActions={waitActions}
                  waitFeedback={waitFeedback}
                  waitOverrides={waitOverrides}
                  waitOverrideDrafts={waitOverrideDrafts}
                  setWaitOverrideDrafts={setWaitOverrideDrafts}
                  waitConfirmation={waitConfirmation}
                  setWaitConfirmation={setWaitConfirmation}
                  onWaitlistCommunicationSummary={updateWaitlistCommunicationSummary}
                  canViewContacts={canViewContacts}
                  canViewSensitive={canViewSensitive}
                  requiresWorkstationReauth={requiresWorkstationReauth}
                  readOnly={readOnly}
                  day={data}
                  now={serverNow}
                  serverNow={serverNow}
                  onSeat={posadz}
                  onPhase={changePhase}
                  onRetry={retryRowAction}
                  onPreviewWaitlist={previewWaitlistOffer}
                  onOfferWaitlist={sendWaitlistOffer}
                  onCancelWaitlistOverride={(entry) => {
                    setWaitOverrides((current) => ({ ...current, [entry.id]: null }))
                    setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: emptyOverrideDraft() }))
                    setWaitFeedback((current) => ({ ...current, [entry.id]: null }))
                  }}
                  onAcceptWaitlist={acceptWaitlistOffer}
                  onWithdrawWaitlist={withdrawWaitlistOffer}
                  onCancelWaitlist={cancelWaitlistEntry}
                  onPriorityWaitlist={toggleWaitlistPriority}
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
  waitDrafts,
  setWaitDrafts,
  waitActions,
  waitFeedback,
  waitOverrides,
  waitOverrideDrafts,
  setWaitOverrideDrafts,
  waitConfirmation,
  setWaitConfirmation,
  onWaitlistCommunicationSummary,
  canViewContacts,
  canViewSensitive,
  requiresWorkstationReauth,
  readOnly,
  day,
  now,
  serverNow,
  onSeat,
  onPhase,
  onRetry,
  onPreviewWaitlist,
  onOfferWaitlist,
  onCancelWaitlistOverride,
  onAcceptWaitlist,
  onWithdrawWaitlist,
  onCancelWaitlist,
  onPriorityWaitlist,
}) {
  const tableName = (id) => tables.find((table) => table.id === id)?.nazwa || `#${id}`
  const tableLabel = (reservation) => {
    const ids = tableIdsFor(reservation)
    return ids.length ? ids.map(tableName).join(' + ') : null
  }
  const availableTables = tables.filter((table) => table.aktywny && table.aktywny_w_planie !== false)
  const empty = !(
    queue?.nadchodzace?.length
    || queue?.na_sali?.length
    || queue?.zakonczone?.length
    || queue?.waitlista?.length
    || queue?.komunikacja_waitlist?.length
  )

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
                id={`host-seat-${reservation.id}`}
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

      {(queue?.waitlista || []).length ? (
        <QueueSection title="Lista oczekujących" count={queue.waitlista.length}>
          {queue.waitlista.map((entry, index) => (
            <WaitlistEntry
              key={entry.id}
              entry={entry}
              position={index + 1}
              tableName={tableName}
              draft={waitDrafts[entry.id]}
              onDraftChange={(patch) => setWaitDrafts((current) => ({
                ...current,
                [entry.id]: { ...current[entry.id], ...patch },
              }))}
              action={waitActions[entry.id]}
              feedback={waitFeedback[entry.id]}
              override={waitOverrides[entry.id]}
              overrideDraft={waitOverrideDrafts[entry.id] || emptyOverrideDraft()}
              onOverrideDraftChange={(value) => setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: value }))}
              confirmation={waitConfirmation?.id === entry.id ? waitConfirmation.type : null}
              setConfirmation={(type) => setWaitConfirmation(type ? { id: entry.id, type } : null)}
              onCommunicationSummary={onWaitlistCommunicationSummary}
              canViewContacts={canViewContacts}
              requiresWorkstationReauth={requiresWorkstationReauth}
              readOnly={readOnly}
              serverNow={serverNow}
              onPreview={() => onPreviewWaitlist(entry)}
              onOffer={() => onOfferWaitlist(entry)}
              onOverrideConfirm={(overrideConfirmation, authorization) => onOfferWaitlist(entry, overrideConfirmation, authorization)}
              onOverrideCancel={() => onCancelWaitlistOverride(entry)}
              onAccept={() => onAcceptWaitlist(entry)}
              onWithdraw={() => onWithdrawWaitlist(entry)}
              onCancel={() => onCancelWaitlist(entry)}
              onPriority={() => onPriorityWaitlist(entry)}
            />
          ))}
        </QueueSection>
      ) : null}

      {canViewContacts && (queue?.komunikacja_waitlist || []).length ? (
        <QueueSection
          title="Komunikacja do wyjaśnienia"
          count={queue.komunikacja_waitlist.length}
          quiet
        >
          {queue.komunikacja_waitlist.map((entry) => (
            <WaitlistCommunicationAttention
              key={entry.id}
              entry={entry}
              readOnly={readOnly}
              onSummaryChange={onWaitlistCommunicationSummary}
            />
          ))}
        </QueueSection>
      ) : null}

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

function WaitlistCommunicationAttention({ entry, readOnly, onSummaryChange }) {
  const [open, setOpen] = useState(false)
  return (
    <article className="border-b border-line py-3 last:border-b-0" aria-labelledby={`waitlist-attention-${entry.id}`}>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p id={`waitlist-attention-${entry.id}`} className="truncate text-sm font-semibold text-ink">
            {entry.nazwisko || 'Gość'}
          </p>
          <p className="mt-1 text-xs text-muted">
            {WAITLIST_TERMINAL_LABELS[entry.status] || 'Wpis zakończony'}
          </p>
        </div>
        <ReservationCommunicationStatus
          summary={entry.communication_summary}
          showChannel={false}
        />
      </div>
      <Button
        variant="subtle"
        size="sm"
        className="mt-3 w-full"
        onClick={() => setOpen((current) => !current)}
        disabled={readOnly}
        aria-expanded={open}
        aria-controls={`host-waitlist-attention-communication-${entry.id}`}
        aria-describedby={readOnly ? 'host-readonly-actions' : undefined}
      >
        <Icon name="bell" className="h-4 w-4" />
        {open ? 'Zwiń historię' : 'Sprawdź komunikację'}
      </Button>
      {open ? (
        <div id={`host-waitlist-attention-communication-${entry.id}`}>
          <ReservationCommunicationPanel
            ownerType="waitlist"
            ownerId={entry.id}
            initialSummary={entry.communication_summary}
            canQueue={false}
            actionsDisabled={readOnly}
            showQueueAction={false}
            onSummaryChange={onSummaryChange}
          />
        </div>
      ) : null}
    </article>
  )
}

const waitMinutes = (entry, serverNow) => {
  const created = parseUtcTimestamp(entry?.utworzono_at)
  return created == null ? null : Math.max(0, Math.floor((serverNow - created) / 60000))
}

function WaitlistEntry({
  entry,
  position,
  tableName,
  draft,
  onDraftChange,
  action,
  feedback,
  override,
  overrideDraft,
  onOverrideDraftChange,
  confirmation,
  setConfirmation,
  onCommunicationSummary,
  canViewContacts,
  requiresWorkstationReauth,
  readOnly,
  serverNow,
  onPreview,
  onOffer,
  onOverrideConfirm,
  onOverrideCancel,
  onAccept,
  onWithdraw,
  onCancel,
  onPriority,
}) {
  const [communicationOpen, setCommunicationOpen] = useState(false)
  const guestName = canViewContacts ? entry.nazwisko : 'Gość'
  const offered = entry.status === 'zaoferowano'
  const timing = offered ? offerTiming(entry, serverNow, readOnly) : null
  const waiting = waitMinutes(entry, serverNow)
  const heldTables = waitlistTableIds(entry).map(tableName).join(' + ')
  const busy = Boolean(action)
  const describedBy = readOnly ? 'host-readonly-actions' : undefined

  return (
    <article className="border-b border-line py-4 last:border-b-0" aria-labelledby={`waitlist-${entry.id}-name`} aria-busy={busy}>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold tabular-nums text-muted">#{position}</span>
            {Number(entry.priorytet) === 1 ? <span className="rounded-full bg-mint/12 px-2 py-0.5 text-[0.68rem] font-semibold text-mint">Priorytet</span> : null}
            {offered ? <span className="rounded-full bg-lemon/12 px-2 py-0.5 text-[0.68rem] font-semibold text-lemon">Zaoferowano</span> : null}
          </div>
          <p id={`waitlist-${entry.id}-name`} className="mt-1 truncate text-sm font-semibold text-ink">{guestName}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            {[entry.godz_od || 'bez preferowanej godziny', entry.liczba_osob ? `${entry.liczba_osob} os.` : null, !offered && waiting != null ? `czeka ${waiting} min` : null].filter(Boolean).join(' · ')}
          </p>
        </div>
        {entry.communication_summary ? <ReservationCommunicationStatus summary={entry.communication_summary} showChannel={false} /> : null}
      </div>

      {offered ? (
        <div className="mt-3 border-y border-line py-3">
          <p className="text-sm font-semibold text-ink">{heldTables || 'Konfiguracja stolików'}</p>
          <p className="mt-1 text-xs text-muted">{[entry.hold_godz_od, entry.hold_godz_do ? `do ${entry.hold_godz_do}` : null].filter(Boolean).join(' · ')}</p>
          <time
            dateTime={entry.hold_do || undefined}
            aria-label={timing?.absolute ? `Oferta wygasa o ${timing.absolute}` : undefined}
            className={`mt-2 block text-xs font-semibold tabular-nums ${timing?.danger ? 'text-danger' : timing?.urgent ? 'text-lemon' : 'text-ink'}`}
          >
            {timing?.text}
          </time>
        </div>
      ) : null}

      {!offered && draft ? (
        <div className="mt-3 border-y border-line py-3">
          <fieldset>
            <legend className="text-xs font-semibold text-ink">Wybierz konfigurację</legend>
            <div className="mt-2 divide-y divide-line">
              {draft.candidates.map((candidate, index) => {
                const selected = candidate.tableIds.join(':') === draft.selectedIds.join(':')
                const names = candidate.tableIds.map(tableName).join(' + ')
                return (
                  <button
                    key={candidate.key}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => onDraftChange({ selectedIds: candidate.tableIds })}
                    disabled={busy || readOnly || Boolean(override)}
                    className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-2 py-2 text-left text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint/60 disabled:opacity-50 ${selected ? 'bg-mint/10 text-ink' : 'text-muted hover:bg-white/[0.05] hover:text-ink'}`}
                  >
                    <span className="min-w-0 break-words font-semibold">{names || `Wariant ${index + 1}`}</span>
                    <span className="shrink-0 text-xs">{selected ? 'Wybrano' : 'Wybierz'}</span>
                  </button>
                )
              })}
            </div>
          </fieldset>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="field-label min-w-0 sm:w-32">
              Ważność oferty
              <select
                value={draft.minutes}
                onChange={(event) => onDraftChange({ minutes: Number(event.target.value) })}
                disabled={busy || readOnly || Boolean(override)}
                className={`${fld} mt-1.5 min-h-11 w-full`}
              >
                {[5, 10, 15, 20].map((minutes) => <option key={minutes} value={minutes}>{minutes} min</option>)}
              </select>
            </label>
            <Button className="w-full sm:flex-1" size="sm" onClick={onOffer} disabled={busy || readOnly || Boolean(override)} loading={action === 'offer'} loadingLabel="Trzymam stoliki…" aria-describedby={describedBy}>
              Wyślij ofertę · {draft.minutes} min
            </Button>
          </div>
        </div>
      ) : null}

      {!offered && !draft ? (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Button variant={position === 1 ? 'primary' : 'ghost'} size="sm" className="w-full" onClick={onPreview} disabled={busy || readOnly} loading={action === 'preview'} loadingLabel="Dobieram…" aria-describedby={describedBy}>
            Dobierz stolik
          </Button>
          <Button variant="subtle" size="sm" className="w-full" onClick={onPriority} disabled={busy || readOnly} loading={action === 'priority'} loadingLabel="Zmieniam…" aria-describedby={describedBy}>
            {Number(entry.priorytet) === 1 ? 'Usuń priorytet' : 'Nadaj priorytet'}
          </Button>
        </div>
      ) : null}

      {offered && !timing?.expired ? (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Button size="sm" className="w-full" onClick={onAccept} disabled={busy || readOnly} loading={action === 'accept'} loadingLabel="Potwierdzam…" aria-describedby={describedBy}>
            Gość przyjął
          </Button>
          <Button variant="ghost" size="sm" className="w-full" onClick={() => setConfirmation('withdraw')} disabled={busy || readOnly} aria-describedby={describedBy}>
            Wycofaj ofertę
          </Button>
        </div>
      ) : null}

      {confirmation ? (
        <div className="mt-3 border-y border-danger/25 bg-danger/[0.04] py-3" role="group" aria-label={confirmation === 'withdraw' ? 'Potwierdź wycofanie oferty' : 'Potwierdź anulowanie oczekiwania'}>
          <p className="px-2 text-xs leading-relaxed text-ink">
            {confirmation === 'withdraw' ? 'Zwolnić stoliki i wycofać ofertę?' : 'Anulować oczekiwanie tego gościa?'}
          </p>
          <div className="mt-2 grid grid-cols-2 gap-2 px-2">
            <Button variant="subtle" size="sm" onClick={() => setConfirmation(null)} disabled={busy}>Zostaw</Button>
            <Button variant="danger" size="sm" onClick={confirmation === 'withdraw' ? onWithdraw : onCancel} disabled={busy} loading={action === confirmation} loadingLabel="Zapisuję…">
              {confirmation === 'withdraw' ? 'Wycofaj' : 'Anuluj'}
            </Button>
          </div>
        </div>
      ) : null}

      {!offered && !confirmation ? (
        <button type="button" onClick={() => setConfirmation('cancel')} disabled={busy || readOnly} aria-describedby={describedBy} className="mt-2 min-h-11 rounded-lg px-2 text-xs font-semibold text-muted underline decoration-current/30 underline-offset-2 transition hover:text-danger disabled:opacity-50">
          Anuluj oczekiwanie
        </button>
      ) : null}

      <InlineFeedback value={feedback} disabled={busy || readOnly} />

      {override ? (
        <ReservationOverridePanel
          availability={override}
          value={overrideDraft}
          onChange={onOverrideDraftChange}
          onCancel={onOverrideCancel}
          onConfirm={onOverrideConfirm}
          busy={action === 'offer'}
          requiresPin={requiresWorkstationReauth}
          reauthError={feedback?.reauthError}
          retryAfter={feedback?.reauthRetryAfter}
          actionLabel={requiresWorkstationReauth ? 'Potwierdź PIN-em i wyślij ofertę' : 'Wyślij ofertę mimo limitu'}
        />
      ) : null}

      {canViewContacts ? (
        <Button
          variant={feedback?.communicationRequired ? 'ghost' : 'subtle'}
          size="sm"
          className="mt-2 w-full"
          onClick={() => setCommunicationOpen((current) => !current)}
          disabled={busy || readOnly}
          aria-expanded={communicationOpen}
          aria-controls={`host-waitlist-communication-${entry.id}`}
          aria-describedby={describedBy}
        >
          <Icon name="bell" className="h-4 w-4" />
          {communicationOpen ? 'Zwiń komunikację' : 'Komunikacja'}
        </Button>
      ) : null}

      {canViewContacts && communicationOpen ? (
        <div id={`host-waitlist-communication-${entry.id}`}>
          <ReservationCommunicationPanel
            ownerType="waitlist"
            ownerId={entry.id}
            initialSummary={entry.communication_summary}
            canQueue={entry.can_queue_communication === true}
            communicationPreference={entry.kanal_komunikacji || 'auto'}
            actionsDisabled={busy || readOnly}
            showQueueAction={offered}
            manualAlreadyHandled={Boolean(entry.powiadomiono_at || entry.communication_summary?.legacy_delivery)}
            onSummaryChange={onCommunicationSummary}
          />
        </div>
      ) : null}
    </article>
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
    <div className={`mt-2 flex min-h-6 flex-wrap items-center gap-2 text-xs ${value.type === 'error' ? 'text-danger' : value.type === 'warning' ? 'text-lemon' : 'text-success'}`} role={value.type === 'error' ? 'alert' : 'status'} aria-live="polite">
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

export { offerSuccessMessage, patchSnapshotReservation, visitTiming }
