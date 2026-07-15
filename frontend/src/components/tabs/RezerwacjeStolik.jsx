import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { DialogFrame } from '../ui/DialogFrame'
import { PillSwitch } from '../ui/PillSwitch'
import { Icon } from '../../lib/icons'
import { api, nowyKluczIdempotencji } from '../../lib/api'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../ui/Toast'
import { warsawDateISO } from '../../lib/date'
import { shiftDateIso } from '../../lib/reservationRoute'
import ReservationAllocationSummary from './ReservationAllocationSummary'
import ReservationOverridePanel from './ReservationOverridePanel'

// Zarządzanie rezerwacjami stolików (admin): lista dnia + formularz + zmiana statusu + stoliki.
// Backend: /api/rezerwacje-stolik, /api/stoliki. Moduł za flagą LokalConfig.modul_rezerwacje.

const num = (v) => (v === '' || v == null ? null : parseInt(v, 10))
const dzisISO = () => warsawDateISO()
const parseDay = (value) => new Date(`${value}T12:00:00`)
const emptyOverrideDraft = () => ({ powod: '', notatka: '' })

const STATUS_META = {
  rezerwacja: {
    label: 'Rezerwacja',
    className: 'bg-lemon/15 text-lemon',
    actions: [
      { status: 'potwierdzona', label: 'Potwierdź', pending: 'Potwierdzam…', icon: 'check' },
      { status: 'odwolana', label: 'Odwołaj', pending: 'Odwołuję…', icon: 'close' },
    ],
  },
  potwierdzona: {
    label: 'Potwierdzona',
    className: 'bg-mint/15 text-mint',
    actions: [
      { status: 'odbyla', label: 'Odbyła się', pending: 'Zapisuję…', icon: 'check' },
      { status: 'no_show', label: 'Nie przyszli', pending: 'Zapisuję…', icon: 'warning' },
      { status: 'odwolana', label: 'Odwołaj', pending: 'Odwołuję…', icon: 'close' },
    ],
  },
  odbyla: { label: 'Odbyła się', className: 'bg-white/10 text-muted', actions: [] },
  no_show: { label: 'Nie przyszli', className: 'bg-danger/15 text-danger', actions: [] },
  odwolana: { label: 'Odwołana', className: 'bg-danger/10 text-muted', actions: [] },
}

const STATUS_FEEDBACK = {
  potwierdzona: 'Potwierdzono rezerwację.',
  odbyla: 'Oznaczono jako odbytą.',
  no_show: 'Oznaczono nieobecność.',
  odwolana: 'Odwołano rezerwację.',
}

const emptyWaitlist = () => ({ godz_od: '', liczba_osob: '', nazwisko: '', telefon: '' })
const RESERVATION_CREATE_MODES = [
  { value: 'reczna', label: 'Rezerwacja' },
  { value: 'walk_in', label: 'Walk-in (gość na miejscu)' },
]
const newReservation = (data) => ({
  data,
  godz_od: '18:00',
  kanal: 'reczna',
  stolik_id: '',
  liczba_osob: '',
  nazwisko: '',
  telefon: '',
  email: '',
  notatka: '',
  zadatek: 0,
})

const sortReservations = (rows) => [...rows].sort((a, b) =>
  (a.godz_od || '').localeCompare(b.godz_od || '') || a.id - b.id)
const sortTables = (rows) => [...rows].sort((a, b) =>
  (a.kolejnosc || 0) - (b.kolejnosc || 0) || a.id - b.id)
const sortWaitlist = (rows) => [...rows].sort((a, b) =>
  (a.status || '').localeCompare(b.status || '') ||
  (a.godz_od || '').localeCompare(b.godz_od || '') || a.id - b.id)

const replaceById = (rows, next, sorter = (value) => value) => {
  const exists = rows.some((row) => row.id === next.id)
  return sorter(exists ? rows.map((row) => row.id === next.id ? next : row) : [...rows, next])
}

const allocationFromDraft = (draft, tables) => {
  const ids = [...new Set([
    draft?.stolik_id,
    ...(draft?.stoliki_dodatkowe || []),
  ].map(Number).filter((id) => Number.isFinite(id) && id > 0))]
  if (!ids.length) return null

  const assignedTables = ids.map((id) => {
    const table = tables.find((item) => Number(item.id) === id)
    return {
      id,
      name: table?.nazwa || `Stolik #${id}`,
      capacity: Number(table?.pojemnosc) || null,
    }
  })
  const sourceTable = tables.find((item) => Number(item.id) === ids[0])
  const roomName = sourceTable?.sala_nazwa || sourceTable?.strefa || null
  const capacity = assignedTables.reduce((sum, table) => sum + (table.capacity || 0), 0)
  const manual = draft?.auto_przydzielony !== true
  return {
    state: manual ? 'manual_locked' : 'assigned',
    visibility: 'exact',
    room: roomName ? { id: sourceTable?.sala_id || null, name: roomName } : null,
    tables: assignedTables,
    capacity: capacity || null,
    visit_end: draft?.godz_do || null,
    reasons: manual ? [{ code: 'MANUAL_LOCK', message: 'Stolik wybrany przez obsługę' }] : [],
  }
}

const reservationSnapshot = (draft) => JSON.stringify([
  draft?.data || '',
  draft?.godz_od || '',
  draft?.kanal || '',
  String(draft?.stolik_id || ''),
  String(draft?.liczba_osob ?? ''),
  draft?.nazwisko || '',
  draft?.telefon || '',
  draft?.email || '',
  draft?.notatka || '',
  String(draft?.zadatek ?? 0),
])

function ReservationSkeleton() {
  return (
    <div className="space-y-2" aria-label="Ładowanie rezerwacji" role="status">
      {[0, 1, 2].map((row) => (
        <div key={row} className="flex min-h-[84px] animate-pulse items-center gap-4 rounded-xl border border-line bg-white/[0.025] px-4 py-3 motion-reduce:animate-none">
          <div className="h-5 w-16 rounded bg-white/[0.07]" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-4 w-36 rounded bg-white/[0.07]" />
            <div className="h-3 w-52 max-w-full rounded bg-white/[0.05]" />
          </div>
          <div className="hidden h-7 w-24 rounded-full bg-white/[0.05] sm:block" />
        </div>
      ))}
      <span className="sr-only">Ładowanie rezerwacji…</span>
    </div>
  )
}

function InlineFeedback({ pending, feedback, className = '' }) {
  const isError = feedback?.type === 'error'
  const isWarning = feedback?.type === 'warning'
  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live="polite"
      className={`min-h-5 text-xs ${isError ? 'text-danger' : isWarning ? 'text-lemon' : feedback?.type === 'success' ? 'text-success' : 'text-muted'} ${className}`}
    >
      {pending || feedback?.message || ''}
    </div>
  )
}

export default function RezerwacjeStolik({
  date: controlledDate,
  onDateChange,
  reservationId,
  onReservationOpen,
  onReservationClose,
  suspendReservationDialog = false,
  onGuestProfileOpen,
  onOpenRooms,
} = {}) {
  const { confirm } = useToast()
  const { can, isAdmin } = useAuth()
  const createModeDescriptionId = useId()
  const maPrawo = (permission) => isAdmin || can(permission)
  const canManageFloor = maPrawo('rezerwacje.sala')
  const canViewContacts = maPrawo('rezerwacje.dane_kontaktowe')
  const canViewNotes = maPrawo('rezerwacje.notatki_wewnetrzne')
  const canViewFinances = maPrawo('rezerwacje.finanse')
  const canOverrideLimits = maPrawo('rezerwacje.nadpisuj_limity')
  const dateControlled = controlledDate !== undefined
  const selectionControlled = reservationId !== undefined
  const [localDate, setLocalDate] = useState(dzisISO())
  const data = dateControlled ? controlledDate : localDate
  const dataRef = useRef(data)
  const loadedDayRef = useRef(null)
  const invalidSelectionRef = useRef(null)
  const [rez, setRez] = useState([])
  const [stoliki, setStoliki] = useState([])
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)
  const requestId = useRef(0)
  const loadControllerRef = useRef(null)
  const mutationGenerationRef = useRef(0)
  const mutationControllersRef = useRef(new Set())
  const piiVisibility = `${canViewContacts}:${canViewNotes}:${canViewFinances}`
  const piiVisibilityRef = useRef(piiVisibility)

  const [modal, setModal] = useState(null)
  const modalInitial = useRef(null)
  const probaZapisuRef = useRef(null)
  const reservationTriggerRef = useRef(null)
  const reservationNameRef = useRef(null)
  const [modalAction, setModalAction] = useState(null)
  const [modalFeedback, setModalFeedback] = useState(null)
  const [modalOverrideDraft, setModalOverrideDraft] = useState(emptyOverrideDraft)
  const [modalAllocationPreview, setModalAllocationPreview] = useState(null)
  const [modalAllocationError, setModalAllocationError] = useState(null)
  const clearModalAllocation = useCallback(() => {
    setModalAllocationPreview(null)
    setModalAllocationError(null)
  }, [])
  const clearModalConflict = () => {
    setModalFeedback(null)
    setModalOverrideDraft(emptyOverrideDraft())
  }
  const updateModalAllocationContext = (patch) => {
    setModal((current) => ({ ...current, ...patch }))
    clearModalConflict()
    clearModalAllocation()
  }
  const [rowActions, setRowActions] = useState({})
  const [rowFeedback, setRowFeedback] = useState({})
  const [pageFeedback, setPageFeedback] = useState(null)

  const [listaModal, setListaModal] = useState(false)
  const waitlistTriggerRef = useRef(null)
  const [nowyOcz, setNowyOcz] = useState(emptyWaitlist)
  const [posadzStolik, setPosadzStolik] = useState({})
  const [waitAdding, setWaitAdding] = useState(false)
  const [waitActions, setWaitActions] = useState({})
  const [waitFeedback, setWaitFeedback] = useState(null)
  const [waitRowFeedback, setWaitRowFeedback] = useState({})
  const [waitOverrides, setWaitOverrides] = useState({})
  const [waitOverrideDrafts, setWaitOverrideDrafts] = useState({})

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

  const startMutation = () => {
    const controller = new AbortController()
    mutationControllersRef.current.add(controller)
    return { controller, generation: mutationGenerationRef.current }
  }
  const mutationIsCurrent = ({ controller, generation }) => (
    !controller.signal.aborted && generation === mutationGenerationRef.current
  )
  const finishMutation = ({ controller }) => mutationControllersRef.current.delete(controller)

  const load = useCallback(async ({ silent = false, day = data } = {}) => {
    loadControllerRef.current?.abort()
    const controller = new AbortController()
    loadControllerRef.current = controller
    const id = ++requestId.current
    if (silent) {
      setRefreshing(true)
      setRefreshError(null)
    } else {
      loadedDayRef.current = null
      setRefreshing(false)
      setLoading(true)
      setLoadError(null)
    }
    try {
      const [rs, ss, lo] = await Promise.all([
        api(`/rezerwacje-stolik?start=${day}&end=${day}`, 'GET', null, { signal: controller.signal }),
        api('/stoliki', 'GET', null, { signal: controller.signal }),
        api(`/lista-oczekujacych?data=${day}`, 'GET', null, { signal: controller.signal }),
      ])
      if (controller.signal.aborted || id !== requestId.current || day !== dataRef.current) return
      loadedDayRef.current = day
      setRez(sortReservations(rs.rezerwacje || []))
      setStoliki(sortTables(ss.stoliki || []))
      setLista(sortWaitlist(lo.lista || []))
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError' || id !== requestId.current || day !== dataRef.current) return
      const message = error.message || 'Nie udało się pobrać rezerwacji.'
      if (silent) setRefreshError(message)
      else setLoadError(message)
    } finally {
      if (controller.signal.aborted || id !== requestId.current || day !== dataRef.current) return
      if (loadControllerRef.current === controller) loadControllerRef.current = null
      setRefreshing(false)
      setLoading(false)
    }
  }, [data, canViewContacts, canViewNotes, canViewFinances])

  useEffect(() => {
    const cancelPrivacyWork = () => {
      cancelReadRequests()
      cancelMutationContinuations()
    }
    const unsubscribe = subscribeReservationPrivacyPurge(cancelPrivacyWork)
    return () => {
      unsubscribe()
      cancelPrivacyWork()
    }
  }, [cancelMutationContinuations, cancelReadRequests])

  useEffect(() => {
    if (!data || dataRef.current === data) return
    dataRef.current = data
    loadedDayRef.current = null
    cancelReadRequests()
    setLoading(true)
    setRefreshing(false)
    setLoadError(null)
    setRefreshError(null)
    setPageFeedback(null)
    setRowFeedback({})
    setPosadzStolik({})
  }, [cancelReadRequests, data])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const visibilityChanged = piiVisibilityRef.current !== piiVisibility
    piiVisibilityRef.current = piiVisibility
    if (!visibilityChanged) return
    cancelMutationContinuations()
    // Otwarty formularz może zawierać zredagowane wartości. Po zmianie praw zamykamy go,
    // a równoległy efekt ``load`` pobiera rekord ponownie przed kolejną edycją.
    modalInitial.current = null
    probaZapisuRef.current = null
    setModalFeedback(null)
    clearModalAllocation()
    setModal(null)
    if (modal || (selectionControlled && reservationId != null)) onReservationClose?.()
  }, [cancelMutationContinuations, clearModalAllocation, piiVisibility])
  const reservationDirty = !!modal && reservationSnapshot(modal) !== modalInitial.current
  const waitDraftDirty = !!(nowyOcz.nazwisko.trim() || nowyOcz.godz_od || nowyOcz.liczba_osob || nowyOcz.telefon.trim())

  useEffect(() => {
    if (!(reservationDirty || waitDraftDirty)) return undefined
    const warn = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [reservationDirty, waitDraftDirty])

  const openReservation = useCallback((value, trigger = null, { notify = true } = {}) => {
    if (!canViewContacts) return
    const draft = { ...value }
    reservationTriggerRef.current = trigger
    modalInitial.current = reservationSnapshot(draft)
    probaZapisuRef.current = null
    setModalFeedback(null)
    setModalOverrideDraft(emptyOverrideDraft())
    clearModalAllocation()
    setModal(draft)
    if (notify && draft.id != null) onReservationOpen?.(draft.id)
  }, [canViewContacts, clearModalAllocation, onReservationOpen])

  const closeReservation = async ({ force = false } = {}) => {
    if (modalAction) return
    if (!force && reservationDirty) {
      const discard = await confirm('Odrzucić niezapisane zmiany w rezerwacji?', {
        title: 'Niezapisane zmiany',
        confirmText: 'Odrzuć zmiany',
        cancelText: 'Wróć do edycji',
      })
      if (!discard) return
    }
    modalInitial.current = null
    probaZapisuRef.current = null
    setModalFeedback(null)
    setModalOverrideDraft(emptyOverrideDraft())
    clearModalAllocation()
    setModal(null)
    onReservationClose?.()
  }

  useEffect(() => {
    if (!selectionControlled) return

    const selectedKey = reservationId == null ? null : String(reservationId)
    if (selectedKey == null) {
      invalidSelectionRef.current = null
      if (modal?.id != null && !reservationDirty && !modalAction) {
        modalInitial.current = null
        probaZapisuRef.current = null
        setModalFeedback(null)
        clearModalAllocation()
        setModal(null)
      }
      return
    }

    if (!canViewContacts || loading || loadError || loadedDayRef.current !== data) return
    const selected = rez.find((row) => String(row.id) === selectedKey)
    if (!selected) {
      if (modal?.id != null && !reservationDirty && !modalAction) {
        modalInitial.current = null
        probaZapisuRef.current = null
        setModalFeedback(null)
        clearModalAllocation()
        setModal(null)
      }
      const invalidKey = `${data}:${selectedKey}`
      if (invalidSelectionRef.current !== invalidKey) {
        invalidSelectionRef.current = invalidKey
        onReservationClose?.()
      }
      return
    }

    invalidSelectionRef.current = null
    if (String(modal?.id) === selectedKey || modalAction || (modal && reservationDirty)) return
    openReservation(selected, null, { notify: false })
  }, [
    canViewContacts,
    clearModalAllocation,
    data,
    loadError,
    loading,
    modal,
    modalAction,
    onReservationClose,
    openReservation,
    reservationDirty,
    reservationId,
    rez,
    selectionControlled,
  ])

  const closeWaitlist = async () => {
    if (waitAdding || Object.keys(waitActions).length) return
    if (waitDraftDirty) {
      const discard = await confirm('Odrzucić rozpoczęty wpis na listę oczekujących?', {
        title: 'Niezapisany wpis',
        confirmText: 'Odrzuć formularz',
        cancelText: 'Wróć',
      })
      if (!discard) return
    }
    setNowyOcz(emptyWaitlist())
    setWaitFeedback(null)
    setWaitOverrides({})
    setWaitOverrideDrafts({})
    setListaModal(false)
  }

  const changeDay = (nextDay) => {
    if (!nextDay || nextDay === data) return
    onDateChange?.(nextDay)
    if (dateControlled) return
    dataRef.current = nextDay
    loadedDayRef.current = null
    cancelReadRequests()
    setLoading(true)
    setRefreshing(false)
    setLoadError(null)
    setRefreshError(null)
    setPageFeedback(null)
    setRowFeedback({})
    setPosadzStolik({})
    setLocalDate(nextDay)
  }

  const przesun = (delta) => {
    changeDay(shiftDateIso(data, delta))
  }

  const stolikNazwa = (id) => stoliki.find((table) => table.id === id)?.nazwa || 'Bez stolika'

  const zaproponujPrzydzial = async () => {
    const partySize = num(modal?.liczba_osob)
    if (!modal || modalAction || modal.stolik_id || !modal.data || !modal.godz_od || !partySize || partySize < 1) return
    setModalAction('allocation')
    clearModalAllocation()
    const mutation = startMutation()
    try {
      const result = await api('/rezerwacje/reguly/symuluj', 'POST', {
        data: modal.data,
        godz_od: modal.godz_od,
        liczba_osob: partySize,
        kanal: 'wewnetrzna',
        sala_id: null,
      }, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      const allocation = result?.allocation || result?.availability?.allocation || null
      const alternatives = result?.alternatives || result?.availability?.alternatives || []
      if (!allocation) {
        const violations = result?.violations || result?.availability?.violations || []
        setModalAllocationError(violations[0]?.message || 'Brak bezpiecznego przydziału dla wybranego terminu.')
        return
      }
      setModalAllocationPreview({
        allocation: {
          ...allocation,
          visit_end: allocation.visit_end || result?.visit_end || result?.godz_do || null,
        },
        alternatives,
      })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      setModalAllocationError(error.message || 'Nie udało się zaproponować przydziału.')
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) setModalAction(null)
    }
  }

  const zapisz = async (nadpisanieLimitow = null) => {
    if (!canViewContacts || !modal || modalAction) return
    if (!modal.nazwisko?.trim()) {
      setModalFeedback({ type: 'error', message: 'Podaj nazwisko lub nazwę klienta.' })
      reservationNameRef.current?.focus()
      return
    }
    if (!modal.data) {
      setModalFeedback({ type: 'error', message: 'Wybierz dzień rezerwacji.' })
      return
    }
    setModalAction('save')
    setModalFeedback(null)
    const mutation = startMutation()
    try {
      const body = {
        data: modal.data,
        godz_od: modal.godz_od || null,
        stolik_id: modal.stolik_id ? Number(modal.stolik_id) : null,
        liczba_osob: num(modal.liczba_osob),
        nazwisko: modal.nazwisko.trim(),
        ...(!modal.id ? { kanal: modal.kanal === 'walk_in' ? 'walk_in' : 'reczna' } : {}),
        ...(!modal.id && !modal.stolik_id && modal.godz_od ? { auto_przydziel: true } : {}),
        ...(canViewContacts ? {
          telefon: modal.telefon?.trim() || null,
          email: modal.email?.trim() || null,
        } : {}),
        ...(canViewNotes ? { notatka: modal.notatka?.trim() || null } : {}),
        ...(canViewFinances ? { zadatek: parseFloat(modal.zadatek) || 0 } : {}),
        ...(nadpisanieLimitow ? {
          przekrocz_limity: true,
          nadpisanie_limitow: nadpisanieLimitow,
        } : {}),
      }
      const fingerprint = JSON.stringify(body)
      if (!modal.id && probaZapisuRef.current?.fingerprint !== fingerprint) {
        probaZapisuRef.current = {
          fingerprint,
          key: nowyKluczIdempotencji('manual-reservation'),
        }
      }
      const saved = modal.id
        ? await api(`/rezerwacje-stolik/${modal.id}`, 'PUT', body, { signal: mutation.controller.signal })
        : await api('/rezerwacje-stolik', 'POST', body, {
          headers: { 'Idempotency-Key': probaZapisuRef.current.key },
          signal: mutation.controller.signal,
        })
      if (!mutationIsCurrent(mutation)) return
      setRez((current) => saved.data === data
        ? replaceById(current, saved, sortReservations)
        : current.filter((row) => row.id !== saved.id))
      setPageFeedback({
        type: 'success',
        message: `${modal.id ? 'Zapisano' : 'Dodano'}: ${canViewContacts ? saved.nazwisko : 'Gość'}${saved.godz_od ? `, ${saved.godz_od}` : ''}.`,
      })
      modalInitial.current = null
      probaZapisuRef.current = null
      clearModalAllocation()
      setModal(null)
      onReservationClose?.()
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      if (error.code === 'IDEMPOTENCY_KEY_REUSED') probaZapisuRef.current = null
      const pacingConflict = ['PACING_RESERVATION_LIMIT', 'PACING_COVERS_LIMIT'].includes(error.code)
        || error.availability?.decision === 'override_required'
        || error.availability?.can_override === true
        || error.availability?.violations?.some((violation) => violation.overrideable_by_operator)
      setModalFeedback({
        type: pacingConflict && canOverrideLimits ? 'warning' : 'error',
        message: error.message || 'Nie udało się zapisać rezerwacji.',
        canOverride: pacingConflict && canOverrideLimits,
        availability: error.availability || null,
      })
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) setModalAction(null)
    }
  }

  const usun = async () => {
    if (!isAdmin || !modal?.id || modalAction) return
    const confirmGeneration = mutationGenerationRef.current
    const approved = await confirm(`Usunąć rezerwację dla „${modal.nazwisko}”? Tej operacji nie można cofnąć.`, {
      title: 'Usuń rezerwację',
      confirmText: 'Usuń rezerwację',
      cancelText: 'Zostaw',
    })
    if (!approved || confirmGeneration !== mutationGenerationRef.current) return
    setModalAction('delete')
    setModalFeedback(null)
    const mutation = startMutation()
    try {
      await api(`/rezerwacje-stolik/${modal.id}`, 'DELETE', null, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      const deletedId = modal.id
      const deletedName = modal.nazwisko
      setRez((current) => current.filter((row) => row.id !== deletedId))
      setPageFeedback({ type: 'success', message: `Usunięto rezerwację: ${deletedName}.` })
      modalInitial.current = null
      setModal(null)
      onReservationClose?.()
      void load({ silent: true })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      setModalFeedback({ type: 'error', message: error.message || 'Nie udało się usunąć rezerwacji.' })
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) setModalAction(null)
    }
  }

  const zmienStatus = async (reservation, action) => {
    if (rowActions[reservation.id]) return
    const operationDay = data
    setRowActions((current) => ({ ...current, [reservation.id]: action.status }))
    setRowFeedback((current) => ({ ...current, [reservation.id]: null }))
    const mutation = startMutation()
    try {
      const saved = await api(`/rezerwacje-stolik/${reservation.id}/status`, 'POST', { status: action.status }, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      if (dataRef.current === operationDay) {
        setRez((current) => replaceById(current, saved, sortReservations))
        setRowFeedback((current) => ({
          ...current,
          [reservation.id]: { type: 'success', message: STATUS_FEEDBACK[action.status] || 'Zapisano status.' },
        }))
        // Odwołanie/no-show może przeoptymalizować inne stoliki. Odświeżamy ten sam dzień
        // tylko wtedy, gdy operator nadal go ogląda.
        void load({ silent: true, day: operationDay })
      }
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      if (dataRef.current === operationDay) {
        setRowFeedback((current) => ({
          ...current,
          [reservation.id]: { type: 'error', message: error.message || 'Nie udało się zmienić statusu.' },
        }))
      }
    } finally {
      finishMutation(mutation)
      if (!mutationIsCurrent(mutation)) return
      setRowActions((current) => {
        const next = { ...current }
        delete next[reservation.id]
        return next
      })
    }
  }

  const wyslijPotwierdzenie = async () => {
    if (!canViewContacts || !modal?.id || modalAction) return
    setModalAction('email')
    setModalFeedback(null)
    const mutation = startMutation()
    try {
      const result = await api(`/rezerwacje-stolik/${modal.id}/wyslij-potwierdzenie`, 'POST', null, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      setModalFeedback({
        type: result.wyslano ? 'success' : 'error',
        message: result.wyslano ? 'Wysłano e-mail z potwierdzeniem.' : (result.powod || 'Nie udało się wysłać e-maila.'),
      })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      setModalFeedback({ type: 'error', message: error.message || 'Nie udało się wysłać e-maila.' })
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) setModalAction(null)
    }
  }

  const dodajOczekujacego = async () => {
    if (!canViewContacts || waitAdding) return
    if (!nowyOcz.nazwisko.trim()) {
      setWaitFeedback({ type: 'error', message: 'Podaj nazwisko lub nazwę klienta.' })
      return
    }
    setWaitAdding(true)
    setWaitFeedback(null)
    const mutation = startMutation()
    try {
      const created = await api('/lista-oczekujacych', 'POST', {
        data,
        godz_od: nowyOcz.godz_od || null,
        liczba_osob: num(nowyOcz.liczba_osob),
        nazwisko: nowyOcz.nazwisko.trim(),
        ...(canViewContacts ? { telefon: nowyOcz.telefon.trim() || null } : {}),
      }, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      setLista((current) => replaceById(current, created, sortWaitlist))
      setNowyOcz(emptyWaitlist())
      setWaitFeedback({ type: 'success', message: `Dodano do oczekujących: ${canViewContacts ? created.nazwisko : 'Gość'}.` })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      setWaitFeedback({ type: 'error', message: error.message || 'Nie udało się dodać wpisu.' })
    } finally {
      finishMutation(mutation)
      if (mutationIsCurrent(mutation)) setWaitAdding(false)
    }
  }

  const usunOczekujacego = async (entry) => {
    if (!isAdmin || waitActions[entry.id]) return
    const confirmGeneration = mutationGenerationRef.current
    const approved = await confirm(`Usunąć „${entry.nazwisko}” z listy oczekujących?`, {
      title: 'Usuń wpis',
      confirmText: 'Usuń wpis',
      cancelText: 'Zostaw',
    })
    if (!approved || confirmGeneration !== mutationGenerationRef.current) return
    setWaitActions((current) => ({ ...current, [entry.id]: 'delete' }))
    setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
    const mutation = startMutation()
    try {
      await api(`/lista-oczekujacych/${entry.id}`, 'DELETE', null, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      setLista((current) => current.filter((item) => item.id !== entry.id))
      setWaitFeedback({ type: 'success', message: `Usunięto wpis: ${entry.nazwisko}.` })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'error', message: error.message || 'Nie udało się usunąć wpisu.' },
      }))
    } finally {
      finishMutation(mutation)
      if (!mutationIsCurrent(mutation)) return
      setWaitActions((current) => {
        const next = { ...current }
        delete next[entry.id]
        return next
      })
    }
  }

  const odwolajOczekujacego = async (entry) => {
    if (waitActions[entry.id]) return
    const confirmGeneration = mutationGenerationRef.current
    const approved = await confirm(`Odwołać oczekiwanie dla „${entry.nazwisko}”?`, {
      title: 'Odwołaj oczekiwanie',
      confirmText: 'Odwołaj',
      cancelText: 'Zostaw',
    })
    if (!approved || confirmGeneration !== mutationGenerationRef.current) return
    setWaitActions((current) => ({ ...current, [entry.id]: 'cancel' }))
    setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
    const mutation = startMutation()
    try {
      const saved = await api(`/lista-oczekujacych/${entry.id}/odwolaj`, 'POST', null, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      setLista((current) => replaceById(current, saved, sortWaitlist))
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'success', message: 'Odwołano oczekiwanie.' },
      }))
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'error', message: error.message || 'Nie udało się odwołać wpisu.' },
      }))
    } finally {
      finishMutation(mutation)
      if (!mutationIsCurrent(mutation)) return
      setWaitActions((current) => {
        const next = { ...current }
        delete next[entry.id]
        return next
      })
    }
  }

  const posadz = async (entry, nadpisanieLimitow = null) => {
    if (waitActions[entry.id]) return
    const tableId = posadzStolik[entry.id]
    if (!tableId) {
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'error', message: 'Wybierz stolik przed posadzeniem gości.' },
      }))
      return
    }
    setWaitActions((current) => ({ ...current, [entry.id]: 'seat' }))
    setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
    const mutation = startMutation()
    try {
      const payload = {
        stolik_id: Number(tableId),
        tryb: 'walk_in',
        ...(nadpisanieLimitow ? {
          przekrocz_limity: true,
          nadpisanie_limitow: nadpisanieLimitow,
        } : {}),
      }
      const result = await api(`/lista-oczekujacych/${entry.id}/zrealizuj`, 'POST', payload, { signal: mutation.controller.signal })
      if (!mutationIsCurrent(mutation)) return
      setLista((current) => replaceById(current, result.wpis, sortWaitlist))
      setRez((current) => result.rezerwacja.data === data
        ? replaceById(current, result.rezerwacja, sortReservations)
        : current)
      setPosadzStolik((current) => ({ ...current, [entry.id]: '' }))
      setWaitOverrides((current) => ({ ...current, [entry.id]: null }))
      setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: emptyOverrideDraft() }))
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'success', message: 'Posadzono gości i utworzono rezerwację.' },
      }))
      setPageFeedback({ type: 'success', message: `Posadzono: ${canViewContacts ? entry.nazwisko : 'Gość'}.` })
    } catch (error) {
      if (!mutationIsCurrent(mutation) || error?.name === 'AbortError') return
      const pacingConflict = ['PACING_RESERVATION_LIMIT', 'PACING_COVERS_LIMIT'].includes(error.code)
        || error.availability?.decision === 'override_required'
        || error.availability?.can_override === true
        || error.availability?.violations?.some((violation) => violation.overrideable_by_operator)
      if (pacingConflict && canOverrideLimits) {
        setWaitOverrides((current) => ({ ...current, [entry.id]: error.availability || { violations: [] } }))
        setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: current[entry.id] || emptyOverrideDraft() }))
      }
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: pacingConflict && canOverrideLimits ? 'warning' : 'error', message: error.message || 'Nie udało się posadzić gości.' },
      }))
    } finally {
      finishMutation(mutation)
      if (!mutationIsCurrent(mutation)) return
      setWaitActions((current) => {
        const next = { ...current }
        delete next[entry.id]
        return next
      })
    }
  }

  const activeReservations = useMemo(() => rez.filter((row) => ['rezerwacja', 'potwierdzona'].includes(row.status)), [rez])
  const activeWaitlist = useMemo(() => lista.filter((entry) => entry.status === 'oczekuje'), [lista])
  const guestCount = activeReservations.reduce((sum, row) => sum + (Number(row.liczba_osob) || 0), 0)
  const dataLabel = parseDay(data).toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' })
  const isToday = data === dzisISO()
  const assignedModalAllocation = allocationFromDraft(modal, stoliki)
  const visibleModalAllocation = assignedModalAllocation || modalAllocationPreview?.allocation || null
  const visibleModalAlternatives = assignedModalAllocation ? [] : modalAllocationPreview?.alternatives || []
  const canProposeAllocation = Boolean(
    modal?.data
    && modal?.godz_od
    && num(modal?.liczba_osob) > 0
    && !modal?.stolik_id,
  )

  return (
    <Card className="p-5 sm:p-8">
      <SectionHeader
        title="Rezerwacje stolików"
        subtitle="Plan dnia, statusy rezerwacji i lista oczekujących."
      >
        <Button
          variant="ghost"
          size="sm"
          onClick={(event) => { waitlistTriggerRef.current = event.currentTarget; setListaModal(true) }}
          disabled={loading || !!loadError}
        >
          <Icon name="clock" className="h-4 w-4" />
          Oczekujący ({activeWaitlist.length})
        </Button>
        {canManageFloor ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={onOpenRooms}
          >
            <Icon name="office" className="h-4 w-4" />
            Konfiguruj sale
          </Button>
        ) : null}
        {canViewContacts ? (
          <Button
            size="sm"
            onClick={(event) => openReservation(newReservation(data), event.currentTarget)}
            disabled={loading || !!loadError}
          >
            <Icon name="plus" className="h-4 w-4" />
            Dodaj rezerwację
          </Button>
        ) : null}
      </SectionHeader>

      <div className="mb-5 border-b border-line pb-5">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="subtle" size="sm" onClick={() => przesun(-1)} aria-label="Poprzedni dzień">
            <span aria-hidden="true" className="text-lg leading-none">‹</span>
          </Button>
          <label htmlFor="reservation-day" className="sr-only">Dzień rezerwacji</label>
          <input
            id="reservation-day"
            type="date"
            value={data}
            onChange={(event) => changeDay(event.target.value)}
            className="field w-auto min-w-[9.5rem] px-3"
          />
          <Button variant="subtle" size="sm" onClick={() => przesun(1)} aria-label="Następny dzień">
            <span aria-hidden="true" className="text-lg leading-none">›</span>
          </Button>
          <Button variant="ghost" size="sm" onClick={() => changeDay(dzisISO())} disabled={isToday}>Dzisiaj</Button>
          <span className="min-w-0 flex-1 text-sm font-medium capitalize text-ink sm:ml-2">{dataLabel}</span>
          <span className="inline-flex min-h-5 items-center gap-1.5 text-xs text-muted" role="status" aria-live="polite">
            {refreshing ? <><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Aktualizuję…</> : null}
          </span>
        </div>
        {!loading && !loadError ? (
          <p className="mt-3 text-xs text-muted">
            {activeReservations.length} {activeReservations.length === 1 ? 'aktywna rezerwacja' : 'aktywnych rezerwacji'}
            {' · '}{guestCount} {guestCount === 1 ? 'gość' : 'gości'}
            {' · '}{activeWaitlist.length} oczekujących
          </p>
        ) : null}
        <InlineFeedback feedback={pageFeedback} className="mt-2" />
      </div>

      {refreshError ? (
        <Banner variant="warn" className="mb-4">
          <div className="flex flex-wrap items-center gap-3">
            <span>Nie udało się odświeżyć danych: {refreshError}</span>
            <Button variant="ghost" size="sm" onClick={() => load({ silent: true })}>Ponów</Button>
          </div>
        </Banner>
      ) : null}

      {loading ? (
        <ReservationSkeleton />
      ) : loadError ? (
        <div role="alert">
          <Banner variant="danger">
            <div className="space-y-3">
              <p>{loadError}</p>
              <Button variant="ghost" size="sm" onClick={() => load()}>Spróbuj ponownie</Button>
            </div>
          </Banner>
        </div>
      ) : rez.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line px-5 py-12 text-center">
          <p className="text-sm font-semibold text-ink">Brak rezerwacji na ten dzień</p>
          <p className="mt-1 text-sm text-muted">{canViewContacts ? 'Dodaj pierwszą rezerwację albo przejdź do innego dnia.' : 'Przejdź do innego dnia, aby sprawdzić plan.'}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {rez.map((reservation) => {
            const meta = STATUS_META[reservation.status] || STATUS_META.rezerwacja
            const guestName = canViewContacts ? reservation.nazwisko : 'Gość'
            const currentAction = rowActions[reservation.id]
            const pendingLabel = meta.actions.find((action) => action.status === currentAction)?.pending
            return (
              <article key={reservation.id} className="rounded-xl border border-line bg-white/[0.025] px-4 py-3">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                  <div className="w-[6.25rem] shrink-0 font-display text-sm font-semibold tabular-nums text-ink">
                    {reservation.godz_od || 'Bez godziny'}
                    {reservation.godz_do ? <span className="text-muted">–{reservation.godz_do}</span> : null}
                  </div>
                  <div className="min-w-[10rem] flex-1">
                    {canViewContacts ? (
                      <button
                        type="button"
                        onClick={(event) => openReservation(reservation, event.currentTarget)}
                        className="-my-2 min-h-11 rounded-lg text-left text-sm font-semibold text-ink transition hover:text-mint"
                        aria-label={`Otwórz rezerwację: ${guestName}`}
                      >
                        {guestName}
                      </button>
                    ) : (
                      <span className="inline-flex min-h-11 items-center text-sm font-semibold text-ink">{guestName}</span>
                    )}
                    <div className="text-xs leading-relaxed text-muted">
                      {stolikNazwa(reservation.stolik_id)}
                      {reservation.liczba_osob ? ` · ${reservation.liczba_osob} os.` : ''}
                      {canViewContacts && reservation.telefon ? ` · ${reservation.telefon}` : ''}
                    </div>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${meta.className}`}>{meta.label}</span>
                  <div className="flex flex-wrap items-center justify-end gap-1.5">
                    {meta.actions.map((action) => (
                      <Button
                        key={action.status}
                        variant="ghost"
                        size="sm"
                        onClick={() => zmienStatus(reservation, action)}
                        disabled={!!currentAction || refreshing}
                        loading={currentAction === action.status}
                        loadingLabel={action.pending}
                      >
                        <Icon name={action.icon} className="h-4 w-4" />
                        {action.label}
                      </Button>
                    ))}
                    {canViewContacts ? (
                      <Button
                        variant="subtle"
                        size="sm"
                        onClick={(event) => openReservation(reservation, event.currentTarget)}
                        disabled={!!currentAction}
                        aria-label={`Edytuj rezerwację: ${guestName}`}
                      >
                        <Icon name="clipboard" className="h-4 w-4" />
                        Edytuj
                      </Button>
                    ) : null}
                  </div>
                </div>
                <InlineFeedback pending={pendingLabel} feedback={rowFeedback[reservation.id]} className="mt-1 text-right" />
              </article>
            )
          })}
        </div>
      )}

      {canViewContacts && modal && !suspendReservationDialog ? (
        <DialogFrame
          title={modal.id ? 'Edytuj rezerwację' : 'Nowa rezerwacja'}
          closeLabel="Zamknij edycję rezerwacji"
          onClose={closeReservation}
          initialFocusRef={reservationNameRef}
          restoreFocusRef={reservationTriggerRef}
        >
          <form onSubmit={(event) => { event.preventDefault(); zapisz() }}>
            {!modal.id ? (
              <div className="mb-5 border-b border-line pb-5">
                <PillSwitch
                  label="Tryb tworzenia rezerwacji"
                  options={RESERVATION_CREATE_MODES}
                  value={modal.kanal === 'walk_in' ? 'walk_in' : 'reczna'}
                  onChange={(kanal) => updateModalAllocationContext({ kanal })}
                  disabled={!!modalAction}
                  aria-describedby={createModeDescriptionId}
                />
                <p id={createModeDescriptionId} aria-live="polite" className="mt-2.5 text-sm leading-relaxed text-muted">
                  {modal.kanal === 'walk_in'
                    ? 'Gość jest już na miejscu. Bez ręcznie wybranego stolika system dobierze bezpieczny przydział przy zapisie.'
                    : 'Zapisz rezerwację na wybrany termin. Stolik możesz wybrać ręcznie albo pozostawić systemowi.'}
                </p>
              </div>
            ) : null}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="field-label">Data
                <input type="date" value={modal.data || ''} disabled={!!modalAction} onChange={(event) => updateModalAllocationContext({ data: event.target.value })} className="field mt-1.5" />
              </label>
              <label className="field-label">Godzina
                <input type="time" value={modal.godz_od || ''} disabled={!!modalAction} onChange={(event) => updateModalAllocationContext({ godz_od: event.target.value })} className="field mt-1.5" />
              </label>
              <label className="field-label">Liczba osób
                <input type="number" min="1" value={modal.liczba_osob ?? ''} disabled={!!modalAction} onChange={(event) => updateModalAllocationContext({ liczba_osob: event.target.value })} className="field mt-1.5" />
              </label>
              <label className="field-label">Stolik
                <select value={modal.stolik_id || ''} disabled={!!modalAction} onChange={(event) => updateModalAllocationContext({ stolik_id: event.target.value, stoliki_dodatkowe: [], auto_przydzielony: false })} className="field mt-1.5">
                  <option value="">Bez stolika</option>
                  {stoliki.filter((table) => table.aktywny).map((table) => (
                    <option key={table.id} value={table.id}>{table.nazwa}{table.strefa ? ` (${table.strefa})` : ''} · {table.pojemnosc} os.</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="mt-4">
              {!modal.stolik_id ? (
                <Button
                  variant="subtle"
                  size="sm"
                  onClick={zaproponujPrzydzial}
                  loading={modalAction === 'allocation'}
                  loadingLabel="Proponuję przydział…"
                  disabled={!canProposeAllocation || Boolean(modalAction)}
                >
                  <Icon name="sparkles" className="h-4 w-4" />
                  Zaproponuj przydział
                </Button>
              ) : null}
              {modalAllocationError ? <p role="alert" className="mt-3 text-sm text-danger">{modalAllocationError}</p> : null}
              {visibleModalAllocation ? (
                <ReservationAllocationSummary
                  className="mt-4"
                  allocation={visibleModalAllocation}
                  alternatives={visibleModalAlternatives}
                />
              ) : null}
            </div>

            <div className="mt-5 border-t border-line pt-5">
              <h4 className="text-sm font-semibold text-ink">Dane gościa</h4>
              <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="field-label sm:col-span-2">Nazwisko / klient
                <input ref={reservationNameRef} value={modal.nazwisko || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, nazwisko: event.target.value })); clearModalConflict() }} className="field mt-1.5" placeholder="np. Nowak" autoComplete="name" />
              </label>
              {canViewContacts ? (
                <>
                  <label className="field-label">Telefon
                    <input type="tel" value={modal.telefon || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, telefon: event.target.value })); clearModalConflict() }} className="field mt-1.5" autoComplete="tel" />
                  </label>
                  <label className="field-label">E-mail
                    <input type="email" value={modal.email || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, email: event.target.value })); clearModalConflict() }} className="field mt-1.5" autoComplete="email" />
                  </label>
                </>
              ) : null}
              {canViewFinances ? (
                <label className="field-label">Zadatek (zł)
                  <input type="number" min="0" step="0.01" value={modal.zadatek ?? 0} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, zadatek: event.target.value })); clearModalConflict() }} className="field mt-1.5" />
                </label>
              ) : null}
              {canViewNotes ? (
                <label className="field-label sm:col-span-2">Notatka
                  <textarea rows={3} value={modal.notatka || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, notatka: event.target.value })); clearModalConflict() }} className="field mt-1.5 resize-y" />
                </label>
              ) : null}
              </div>
            </div>

            {canViewContacts && modal.id && modal.email ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={wyslijPotwierdzenie}
                disabled={!!modalAction}
                loading={modalAction === 'email'}
                loadingLabel="Wysyłam e-mail…"
                className="mt-4"
              >
                <Icon name="bell" className="h-4 w-4" />
                Wyślij potwierdzenie
              </Button>
            ) : null}

            <InlineFeedback
              pending={modalAction === 'save' ? 'Zapisuję rezerwację…' : modalAction === 'delete' ? 'Usuwam rezerwację…' : null}
              feedback={modalFeedback}
              className="mt-3"
            />

            {modalFeedback?.canOverride ? (
              <ReservationOverridePanel
                availability={modalFeedback.availability}
                value={modalOverrideDraft}
                onChange={setModalOverrideDraft}
                onCancel={() => {
                  setModalFeedback(null)
                  setModalOverrideDraft(emptyOverrideDraft())
                }}
                onConfirm={zapisz}
                busy={modalAction === 'save'}
              />
            ) : null}

            <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
              {modal.id && onGuestProfileOpen ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onGuestProfileOpen(modal.id)}
                  disabled={!!modalAction}
                >
                  <Icon name="users" className="h-4 w-4" />
                  Karta gościa
                </Button>
              ) : null}
              {isAdmin && modal.id ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={usun}
                  disabled={!!modalAction}
                  loading={modalAction === 'delete'}
                  loadingLabel="Usuwam…"
                  className="border-danger/25 text-danger hover:bg-danger/10"
                >
                  <Icon name="trash" className="h-4 w-4" />
                  Usuń
                </Button>
              ) : null}
              <div className="ml-auto flex flex-wrap justify-end gap-2">
                <Button variant="subtle" size="sm" onClick={closeReservation} disabled={!!modalAction}>Anuluj</Button>
                <Button type="submit" size="sm" loading={modalAction === 'save'} loadingLabel="Zapisuję…" disabled={!!modalAction && modalAction !== 'save'}>
                  <Icon name="check" className="h-4 w-4" />
                  {modalFeedback?.type === 'error' ? 'Ponów zapis' : 'Zapisz'}
                </Button>
              </div>
            </div>
          </form>
        </DialogFrame>
      ) : null}

      {listaModal ? (
        <DialogFrame title={`Lista oczekujących · ${data}`} closeLabel="Zamknij listę oczekujących" onClose={closeWaitlist} maxWidth="max-w-xl" restoreFocusRef={waitlistTriggerRef}>
          <div className="mb-5 space-y-2">
            {lista.length === 0 ? <p className="text-sm text-muted">Nikt nie oczekuje w tym dniu.</p> : null}
            {lista.map((entry) => {
              const action = waitActions[entry.id]
              const guestName = canViewContacts ? entry.nazwisko : 'Gość'
              return (
                <div key={entry.id} className="border-b border-line py-3 last:border-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 text-sm text-ink">
                      <span className="font-semibold">{guestName}</span>
                      {entry.godz_od ? ` · ${entry.godz_od}` : ''}
                      {entry.liczba_osob ? ` · ${entry.liczba_osob} os.` : ''}
                      {canViewContacts && entry.telefon ? ` · ${entry.telefon}` : ''}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {entry.status !== 'oczekuje' ? (
                        <span className={`rounded-full px-2 py-1 text-xs ${entry.status === 'zrealizowany' ? 'bg-mint/15 text-mint' : 'bg-white/10 text-muted'}`}>
                          {entry.status === 'zrealizowany' ? 'Posadzony' : 'Odwołany'}
                        </span>
                      ) : null}
                      {isAdmin ? (
                        <Button
                          variant="subtle"
                          size="sm"
                          onClick={() => usunOczekujacego(entry)}
                          disabled={!!action}
                          loading={action === 'delete'}
                          loadingLabel="Usuwam…"
                          className="px-2 text-muted hover:text-danger"
                          aria-label={`Usuń z listy oczekujących: ${guestName}`}
                        >
                          <Icon name="trash" className="h-4 w-4" />
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  {entry.status === 'oczekuje' ? (
                    <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                      <label className="min-w-0 flex-1">
                        <span className="sr-only">Stolik dla {guestName}</span>
                        <select
                          value={posadzStolik[entry.id] || ''}
                          onChange={(event) => {
                            setPosadzStolik((current) => ({ ...current, [entry.id]: event.target.value }))
                            setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
                            setWaitOverrides((current) => ({ ...current, [entry.id]: null }))
                            setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: emptyOverrideDraft() }))
                          }}
                          disabled={!!action}
                          className="field"
                        >
                          <option value="">Wybierz stolik</option>
                          {stoliki.filter((table) => table.aktywny).map((table) => (
                            <option key={table.id} value={table.id}>{table.nazwa} · {table.pojemnosc} os.</option>
                          ))}
                        </select>
                      </label>
                      <Button
                        size="sm"
                        onClick={() => posadz(entry)}
                        disabled={!!action}
                        loading={action === 'seat'}
                        loadingLabel="Sadzam…"
                      >
                        Posadź
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => odwolajOczekujacego(entry)}
                        disabled={!!action}
                        loading={action === 'cancel'}
                        loadingLabel="Odwołuję…"
                      >
                        Odwołaj
                      </Button>
                    </div>
                  ) : null}
                  <InlineFeedback
                    pending={action === 'seat' ? 'Tworzę rezerwację…' : action === 'cancel' ? 'Odwołuję oczekiwanie…' : action === 'delete' ? 'Usuwam wpis…' : null}
                    feedback={waitRowFeedback[entry.id]}
                    className="mt-2"
                  />
                  {waitOverrides[entry.id] ? (
                    <ReservationOverridePanel
                      availability={waitOverrides[entry.id]}
                      value={waitOverrideDrafts[entry.id] || emptyOverrideDraft()}
                      onChange={(value) => setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: value }))}
                      onCancel={() => {
                        setWaitOverrides((current) => ({ ...current, [entry.id]: null }))
                        setWaitOverrideDrafts((current) => ({ ...current, [entry.id]: emptyOverrideDraft() }))
                        setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
                      }}
                      onConfirm={(override) => posadz(entry, override)}
                      busy={action === 'seat'}
                      actionLabel="Posadź mimo limitu"
                    />
                  ) : null}
                </div>
              )
            })}
          </div>

          {canViewContacts ? (
            <form onSubmit={(event) => { event.preventDefault(); dodajOczekujacego() }} className="border-t border-line pt-5">
              <h4 className="mb-4 text-sm font-semibold text-ink">Dodaj oczekujących</h4>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <label className="field-label sm:col-span-2">Nazwisko / klient
                  <input value={nowyOcz.nazwisko} disabled={waitAdding} onChange={(event) => { setNowyOcz((current) => ({ ...current, nazwisko: event.target.value })); setWaitFeedback(null) }} className="field mt-1.5" autoComplete="name" />
                </label>
              <label className="field-label">Preferowana godzina
                <input type="time" value={nowyOcz.godz_od} disabled={waitAdding} onChange={(event) => { setNowyOcz((current) => ({ ...current, godz_od: event.target.value })); setWaitFeedback(null) }} className="field mt-1.5" />
              </label>
              <label className="field-label">Liczba osób
                <input type="number" min="1" value={nowyOcz.liczba_osob} disabled={waitAdding} onChange={(event) => { setNowyOcz((current) => ({ ...current, liczba_osob: event.target.value })); setWaitFeedback(null) }} className="field mt-1.5" />
              </label>
                <label className="field-label sm:col-span-2">Telefon
                  <input type="tel" value={nowyOcz.telefon} disabled={waitAdding} onChange={(event) => { setNowyOcz((current) => ({ ...current, telefon: event.target.value })); setWaitFeedback(null) }} className="field mt-1.5" autoComplete="tel" />
                </label>
              </div>
              <InlineFeedback pending={waitAdding ? 'Dodaję do listy…' : null} feedback={waitFeedback} className="mt-3" />
              <div className="mt-4 flex justify-end">
                <Button type="submit" size="sm" loading={waitAdding} loadingLabel="Dodaję…">
                  <Icon name="plus" className="h-4 w-4" />
                  {waitFeedback?.type === 'error' ? 'Ponów dodanie' : 'Dodaj do listy'}
                </Button>
              </div>
            </form>
          ) : null}
        </DialogFrame>
      ) : null}
    </Card>
  )
}
