import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Zarządzanie rezerwacjami stolików (admin): lista dnia + formularz + zmiana statusu + stoliki.
// Backend: /api/rezerwacje-stolik, /api/stoliki. Moduł za flagą LokalConfig.modul_rezerwacje.

const num = (v) => (v === '' || v == null ? null : parseInt(v, 10))
const dzisISO = () => {
  const today = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`
}
const parseDay = (value) => new Date(`${value}T12:00:00`)

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

const emptyTable = () => ({ nazwa: '', strefa: '', pojemnosc: 2, rewir_nr: '' })
const emptyWaitlist = () => ({ godz_od: '', liczba_osob: '', nazwisko: '', telefon: '' })
const newReservation = (data) => ({
  data,
  godz_od: '18:00',
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

const reservationSnapshot = (draft) => JSON.stringify([
  draft?.data || '',
  draft?.godz_od || '',
  String(draft?.stolik_id || ''),
  String(draft?.liczba_osob ?? ''),
  draft?.nazwisko || '',
  draft?.telefon || '',
  draft?.email || '',
  draft?.notatka || '',
  String(draft?.zadatek ?? 0),
])

function DialogFrame({ title, closeLabel, onClose, maxWidth = 'max-w-md', initialFocusRef, restoreFocusRef, children }) {
  const titleId = useId()
  const panelRef = useRef(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    const previousFocus = document.activeElement
    const panel = panelRef.current
    const focusableSelector = [
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(',')
    const initial = initialFocusRef?.current || panel?.querySelector(focusableSelector)
    initial?.focus()

    const onKeyDown = (event) => {
      // Modal potwierdzenia ToastProvider ma pierwszeństwo przed formularzem pod spodem.
      if (document.querySelector('[role="alertdialog"]')) return
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current?.()
        return
      }
      if (event.key !== 'Tab' || !panel) return
      const focusable = [...panel.querySelectorAll(focusableSelector)]
        .filter((node) => node.getClientRects().length > 0)
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      requestAnimationFrame(() => {
        const restoreTarget = restoreFocusRef?.current || previousFocus
        if (restoreTarget?.isConnected) restoreTarget.focus()
      })
    }
  }, [initialFocusRef, restoreFocusRef])

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`material max-h-[90dvh] w-full ${maxWidth} overflow-y-auto p-5 shadow-soft sm:p-6`}
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <h3 id={titleId} className="font-display text-lg font-semibold text-ink">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="-m-2 grid min-h-11 min-w-11 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-white/[0.06] hover:text-ink"
            aria-label={closeLabel}
          >
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

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
  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live="polite"
      className={`min-h-5 text-xs ${isError ? 'text-danger' : feedback?.type === 'success' ? 'text-success' : 'text-muted'} ${className}`}
    >
      {pending || feedback?.message || ''}
    </div>
  )
}

export default function RezerwacjeStolik() {
  const { confirm } = useToast()
  const [data, setData] = useState(dzisISO())
  const [rez, setRez] = useState([])
  const [stoliki, setStoliki] = useState([])
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)
  const requestId = useRef(0)

  const [modal, setModal] = useState(null)
  const modalInitial = useRef(null)
  const reservationTriggerRef = useRef(null)
  const reservationNameRef = useRef(null)
  const [modalAction, setModalAction] = useState(null)
  const [modalFeedback, setModalFeedback] = useState(null)
  const [rowActions, setRowActions] = useState({})
  const [rowFeedback, setRowFeedback] = useState({})
  const [pageFeedback, setPageFeedback] = useState(null)

  const [stolikModal, setStolikModal] = useState(false)
  const tableTriggerRef = useRef(null)
  const [nowyStolik, setNowyStolik] = useState(emptyTable)
  const [saleLokalu, setSaleLokalu] = useState([])
  const [tableAdding, setTableAdding] = useState(false)
  const [tableActions, setTableActions] = useState({})
  const [tableFeedback, setTableFeedback] = useState(null)
  const [tableRowFeedback, setTableRowFeedback] = useState({})

  const [listaModal, setListaModal] = useState(false)
  const waitlistTriggerRef = useRef(null)
  const [nowyOcz, setNowyOcz] = useState(emptyWaitlist)
  const [posadzStolik, setPosadzStolik] = useState({})
  const [waitAdding, setWaitAdding] = useState(false)
  const [waitActions, setWaitActions] = useState({})
  const [waitFeedback, setWaitFeedback] = useState(null)
  const [waitRowFeedback, setWaitRowFeedback] = useState({})

  const load = useCallback(async ({ silent = false, day = data } = {}) => {
    const id = ++requestId.current
    if (silent) {
      setRefreshing(true)
      setRefreshError(null)
    } else {
      setLoading(true)
      setLoadError(null)
    }
    try {
      const [rs, ss, lo] = await Promise.all([
        api(`/rezerwacje-stolik?start=${day}&end=${day}`),
        api('/stoliki'),
        api(`/lista-oczekujacych?data=${day}`),
      ])
      if (id !== requestId.current) return
      setRez(sortReservations(rs.rezerwacje || []))
      setStoliki(sortTables(ss.stoliki || []))
      setLista(sortWaitlist(lo.lista || []))
    } catch (error) {
      if (id !== requestId.current) return
      const message = error.message || 'Nie udało się pobrać rezerwacji.'
      if (silent) setRefreshError(message)
      else setLoadError(message)
    } finally {
      if (id !== requestId.current) return
      if (silent) setRefreshing(false)
      else setLoading(false)
    }
  }, [data])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    api('/lokal/config').then((config) => setSaleLokalu(config.sale || [])).catch(() => {})
  }, [])

  const reservationDirty = !!modal && reservationSnapshot(modal) !== modalInitial.current
  const tableDraftDirty = !!(nowyStolik.nazwa.trim() || nowyStolik.strefa.trim() || nowyStolik.rewir_nr || Number(nowyStolik.pojemnosc) !== 2)
  const waitDraftDirty = !!(nowyOcz.nazwisko.trim() || nowyOcz.godz_od || nowyOcz.liczba_osob || nowyOcz.telefon.trim())

  useEffect(() => {
    if (!(reservationDirty || tableDraftDirty || waitDraftDirty)) return undefined
    const warn = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [reservationDirty, tableDraftDirty, waitDraftDirty])

  const openReservation = (value, trigger = null) => {
    const draft = { ...value }
    reservationTriggerRef.current = trigger
    modalInitial.current = reservationSnapshot(draft)
    setModalFeedback(null)
    setModal(draft)
  }

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
    setModalFeedback(null)
    setModal(null)
  }

  const closeTables = async () => {
    if (tableAdding || Object.keys(tableActions).length) return
    if (tableDraftDirty) {
      const discard = await confirm('Odrzucić rozpoczęty formularz nowego stolika?', {
        title: 'Niezapisany stolik',
        confirmText: 'Odrzuć formularz',
        cancelText: 'Wróć',
      })
      if (!discard) return
    }
    setNowyStolik(emptyTable())
    setTableFeedback(null)
    setStolikModal(false)
  }

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
    setListaModal(false)
  }

  const changeDay = (nextDay) => {
    if (!nextDay || nextDay === data) return
    setPageFeedback(null)
    setRowFeedback({})
    setPosadzStolik({})
    setData(nextDay)
  }

  const przesun = (delta) => {
    const next = parseDay(data)
    next.setDate(next.getDate() + delta)
    changeDay(next.toISOString().slice(0, 10))
  }

  const stolikNazwa = (id) => stoliki.find((table) => table.id === id)?.nazwa || 'Bez stolika'

  const zapisz = async () => {
    if (!modal || modalAction) return
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
    try {
      const body = {
        data: modal.data,
        godz_od: modal.godz_od || null,
        stolik_id: modal.stolik_id ? Number(modal.stolik_id) : null,
        liczba_osob: num(modal.liczba_osob),
        nazwisko: modal.nazwisko.trim(),
        telefon: modal.telefon?.trim() || null,
        email: modal.email?.trim() || null,
        notatka: modal.notatka?.trim() || null,
        zadatek: parseFloat(modal.zadatek) || 0,
      }
      const saved = modal.id
        ? await api(`/rezerwacje-stolik/${modal.id}`, 'PUT', body)
        : await api('/rezerwacje-stolik', 'POST', body)
      setRez((current) => saved.data === data
        ? replaceById(current, saved, sortReservations)
        : current.filter((row) => row.id !== saved.id))
      setPageFeedback({
        type: 'success',
        message: `${modal.id ? 'Zapisano' : 'Dodano'}: ${saved.nazwisko}${saved.godz_od ? `, ${saved.godz_od}` : ''}.`,
      })
      modalInitial.current = null
      setModal(null)
    } catch (error) {
      setModalFeedback({ type: 'error', message: error.message || 'Nie udało się zapisać rezerwacji.' })
    } finally {
      setModalAction(null)
    }
  }

  const usun = async () => {
    if (!modal?.id || modalAction) return
    const approved = await confirm(`Usunąć rezerwację dla „${modal.nazwisko}”? Tej operacji nie można cofnąć.`, {
      title: 'Usuń rezerwację',
      confirmText: 'Usuń rezerwację',
      cancelText: 'Zostaw',
    })
    if (!approved) return
    setModalAction('delete')
    setModalFeedback(null)
    try {
      await api(`/rezerwacje-stolik/${modal.id}`, 'DELETE')
      const deletedId = modal.id
      const deletedName = modal.nazwisko
      setRez((current) => current.filter((row) => row.id !== deletedId))
      setPageFeedback({ type: 'success', message: `Usunięto rezerwację: ${deletedName}.` })
      modalInitial.current = null
      setModal(null)
      void load({ silent: true })
    } catch (error) {
      setModalFeedback({ type: 'error', message: error.message || 'Nie udało się usunąć rezerwacji.' })
    } finally {
      setModalAction(null)
    }
  }

  const zmienStatus = async (reservation, action) => {
    if (rowActions[reservation.id]) return
    setRowActions((current) => ({ ...current, [reservation.id]: action.status }))
    setRowFeedback((current) => ({ ...current, [reservation.id]: null }))
    try {
      const saved = await api(`/rezerwacje-stolik/${reservation.id}/status`, 'POST', { status: action.status })
      setRez((current) => replaceById(current, saved, sortReservations))
      setRowFeedback((current) => ({
        ...current,
        [reservation.id]: { type: 'success', message: STATUS_FEEDBACK[action.status] || 'Zapisano status.' },
      }))
      // Odwołanie/no-show może przeoptymalizować inne stoliki. Odświeżamy w tle bez znikania listy.
      void load({ silent: true })
    } catch (error) {
      setRowFeedback((current) => ({
        ...current,
        [reservation.id]: { type: 'error', message: error.message || 'Nie udało się zmienić statusu.' },
      }))
    } finally {
      setRowActions((current) => {
        const next = { ...current }
        delete next[reservation.id]
        return next
      })
    }
  }

  const wyslijPotwierdzenie = async () => {
    if (!modal?.id || modalAction) return
    setModalAction('email')
    setModalFeedback(null)
    try {
      const result = await api(`/rezerwacje-stolik/${modal.id}/wyslij-potwierdzenie`, 'POST')
      setModalFeedback({
        type: result.wyslano ? 'success' : 'error',
        message: result.wyslano ? 'Wysłano e-mail z potwierdzeniem.' : (result.powod || 'Nie udało się wysłać e-maila.'),
      })
    } catch (error) {
      setModalFeedback({ type: 'error', message: error.message || 'Nie udało się wysłać e-maila.' })
    } finally {
      setModalAction(null)
    }
  }

  const dodajStolik = async () => {
    if (tableAdding) return
    if (!nowyStolik.nazwa.trim()) {
      setTableFeedback({ type: 'error', message: 'Podaj nazwę stolika.' })
      return
    }
    setTableAdding(true)
    setTableFeedback(null)
    try {
      const created = await api('/stoliki', 'POST', {
        nazwa: nowyStolik.nazwa.trim(),
        strefa: nowyStolik.strefa.trim() || null,
        pojemnosc: Number(nowyStolik.pojemnosc) || 2,
        rewir_nr: nowyStolik.rewir_nr ? Number(nowyStolik.rewir_nr) : null,
      })
      setStoliki((current) => replaceById(current, created, sortTables))
      setNowyStolik(emptyTable())
      setTableFeedback({ type: 'success', message: `Dodano stolik: ${created.nazwa}.` })
    } catch (error) {
      setTableFeedback({ type: 'error', message: error.message || 'Nie udało się dodać stolika.' })
    } finally {
      setTableAdding(false)
    }
  }

  const usunStolik = async (table) => {
    if (tableActions[table.id]) return
    const approved = await confirm(`Usunąć stolik „${table.nazwa}”? Rezerwacje przypisane do niego pozostaną bez stolika.`, {
      title: 'Usuń stolik',
      confirmText: 'Usuń stolik',
      cancelText: 'Zostaw',
    })
    if (!approved) return
    setTableActions((current) => ({ ...current, [table.id]: 'delete' }))
    setTableRowFeedback((current) => ({ ...current, [table.id]: null }))
    try {
      await api(`/stoliki/${table.id}`, 'DELETE')
      setStoliki((current) => current.filter((item) => item.id !== table.id))
      setRez((current) => current.map((reservation) =>
        reservation.stolik_id === table.id ? { ...reservation, stolik_id: null } : reservation))
      setTableFeedback({ type: 'success', message: `Usunięto stolik: ${table.nazwa}.` })
      void load({ silent: true })
    } catch (error) {
      setTableRowFeedback((current) => ({
        ...current,
        [table.id]: { type: 'error', message: error.message || 'Nie udało się usunąć stolika.' },
      }))
    } finally {
      setTableActions((current) => {
        const next = { ...current }
        delete next[table.id]
        return next
      })
    }
  }

  const dodajOczekujacego = async () => {
    if (waitAdding) return
    if (!nowyOcz.nazwisko.trim()) {
      setWaitFeedback({ type: 'error', message: 'Podaj nazwisko lub nazwę klienta.' })
      return
    }
    setWaitAdding(true)
    setWaitFeedback(null)
    try {
      const created = await api('/lista-oczekujacych', 'POST', {
        data,
        godz_od: nowyOcz.godz_od || null,
        liczba_osob: num(nowyOcz.liczba_osob),
        nazwisko: nowyOcz.nazwisko.trim(),
        telefon: nowyOcz.telefon.trim() || null,
      })
      setLista((current) => replaceById(current, created, sortWaitlist))
      setNowyOcz(emptyWaitlist())
      setWaitFeedback({ type: 'success', message: `Dodano do oczekujących: ${created.nazwisko}.` })
    } catch (error) {
      setWaitFeedback({ type: 'error', message: error.message || 'Nie udało się dodać wpisu.' })
    } finally {
      setWaitAdding(false)
    }
  }

  const usunOczekujacego = async (entry) => {
    if (waitActions[entry.id]) return
    const approved = await confirm(`Usunąć „${entry.nazwisko}” z listy oczekujących?`, {
      title: 'Usuń wpis',
      confirmText: 'Usuń wpis',
      cancelText: 'Zostaw',
    })
    if (!approved) return
    setWaitActions((current) => ({ ...current, [entry.id]: 'delete' }))
    setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
    try {
      await api(`/lista-oczekujacych/${entry.id}`, 'DELETE')
      setLista((current) => current.filter((item) => item.id !== entry.id))
      setWaitFeedback({ type: 'success', message: `Usunięto wpis: ${entry.nazwisko}.` })
    } catch (error) {
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'error', message: error.message || 'Nie udało się usunąć wpisu.' },
      }))
    } finally {
      setWaitActions((current) => {
        const next = { ...current }
        delete next[entry.id]
        return next
      })
    }
  }

  const odwolajOczekujacego = async (entry) => {
    if (waitActions[entry.id]) return
    const approved = await confirm(`Odwołać oczekiwanie dla „${entry.nazwisko}”?`, {
      title: 'Odwołaj oczekiwanie',
      confirmText: 'Odwołaj',
      cancelText: 'Zostaw',
    })
    if (!approved) return
    setWaitActions((current) => ({ ...current, [entry.id]: 'cancel' }))
    setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
    try {
      const saved = await api(`/lista-oczekujacych/${entry.id}/odwolaj`, 'POST')
      setLista((current) => replaceById(current, saved, sortWaitlist))
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'success', message: 'Odwołano oczekiwanie.' },
      }))
    } catch (error) {
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'error', message: error.message || 'Nie udało się odwołać wpisu.' },
      }))
    } finally {
      setWaitActions((current) => {
        const next = { ...current }
        delete next[entry.id]
        return next
      })
    }
  }

  const posadz = async (entry) => {
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
    try {
      const result = await api(`/lista-oczekujacych/${entry.id}/zrealizuj`, 'POST', { stolik_id: Number(tableId) })
      setLista((current) => replaceById(current, result.wpis, sortWaitlist))
      setRez((current) => result.rezerwacja.data === data
        ? replaceById(current, result.rezerwacja, sortReservations)
        : current)
      setPosadzStolik((current) => ({ ...current, [entry.id]: '' }))
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'success', message: 'Posadzono gości i utworzono rezerwację.' },
      }))
      setPageFeedback({ type: 'success', message: `Posadzono: ${entry.nazwisko}.` })
    } catch (error) {
      setWaitRowFeedback((current) => ({
        ...current,
        [entry.id]: { type: 'error', message: error.message || 'Nie udało się posadzić gości.' },
      }))
    } finally {
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

  return (
    <Card className="p-5 sm:p-8">
      <SectionHeader
        title="Rezerwacje stolików"
        subtitle="Plan dnia, statusy rezerwacji, lista oczekujących i konfiguracja stolików."
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
        <Button
          variant="ghost"
          size="sm"
          onClick={(event) => { tableTriggerRef.current = event.currentTarget; setStolikModal(true) }}
          disabled={loading || !!loadError}
        >
          <Icon name="pin" className="h-4 w-4" />
          Stoliki ({stoliki.length})
        </Button>
        <Button
          size="sm"
          onClick={(event) => openReservation(newReservation(data), event.currentTarget)}
          disabled={loading || !!loadError}
        >
          <Icon name="plus" className="h-4 w-4" />
          Dodaj rezerwację
        </Button>
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
          <p className="mt-1 text-sm text-muted">Dodaj pierwszą rezerwację albo przejdź do innego dnia.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {rez.map((reservation) => {
            const meta = STATUS_META[reservation.status] || STATUS_META.rezerwacja
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
                    <button
                      type="button"
                      onClick={(event) => openReservation(reservation, event.currentTarget)}
                      className="-my-2 min-h-11 rounded-lg text-left text-sm font-semibold text-ink transition hover:text-mint"
                      aria-label={`Otwórz rezerwację: ${reservation.nazwisko}`}
                    >
                      {reservation.nazwisko}
                    </button>
                    <div className="text-xs leading-relaxed text-muted">
                      {stolikNazwa(reservation.stolik_id)}
                      {reservation.liczba_osob ? ` · ${reservation.liczba_osob} os.` : ''}
                      {reservation.telefon ? ` · ${reservation.telefon}` : ''}
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
                    <Button
                      variant="subtle"
                      size="sm"
                      onClick={(event) => openReservation(reservation, event.currentTarget)}
                      disabled={!!currentAction}
                      aria-label={`Edytuj rezerwację: ${reservation.nazwisko}`}
                    >
                      <Icon name="clipboard" className="h-4 w-4" />
                      Edytuj
                    </Button>
                  </div>
                </div>
                <InlineFeedback pending={pendingLabel} feedback={rowFeedback[reservation.id]} className="mt-1 text-right" />
              </article>
            )
          })}
        </div>
      )}

      {modal ? (
        <DialogFrame
          title={modal.id ? 'Edytuj rezerwację' : 'Nowa rezerwacja'}
          closeLabel="Zamknij edycję rezerwacji"
          onClose={closeReservation}
          initialFocusRef={reservationNameRef}
          restoreFocusRef={reservationTriggerRef}
        >
          <form onSubmit={(event) => { event.preventDefault(); zapisz() }}>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="field-label">Data
                <input type="date" value={modal.data || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, data: event.target.value })); setModalFeedback(null) }} className="field mt-1.5" />
              </label>
              <label className="field-label">Godzina
                <input type="time" value={modal.godz_od || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, godz_od: event.target.value })); setModalFeedback(null) }} className="field mt-1.5" />
              </label>
              <label className="field-label">Stolik
                <select value={modal.stolik_id || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, stolik_id: event.target.value })); setModalFeedback(null) }} className="field mt-1.5">
                  <option value="">Bez stolika</option>
                  {stoliki.filter((table) => table.aktywny).map((table) => (
                    <option key={table.id} value={table.id}>{table.nazwa}{table.strefa ? ` (${table.strefa})` : ''} · {table.pojemnosc} os.</option>
                  ))}
                </select>
              </label>
              <label className="field-label">Liczba osób
                <input type="number" min="1" value={modal.liczba_osob ?? ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, liczba_osob: event.target.value })); setModalFeedback(null) }} className="field mt-1.5" />
              </label>
              <label className="field-label sm:col-span-2">Nazwisko / klient
                <input ref={reservationNameRef} value={modal.nazwisko || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, nazwisko: event.target.value })); setModalFeedback(null) }} className="field mt-1.5" placeholder="np. Nowak" autoComplete="name" />
              </label>
              <label className="field-label">Telefon
                <input type="tel" value={modal.telefon || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, telefon: event.target.value })); setModalFeedback(null) }} className="field mt-1.5" autoComplete="tel" />
              </label>
              <label className="field-label">E-mail
                <input type="email" value={modal.email || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, email: event.target.value })); setModalFeedback(null) }} className="field mt-1.5" autoComplete="email" />
              </label>
              <label className="field-label">Zadatek (zł)
                <input type="number" min="0" step="0.01" value={modal.zadatek ?? 0} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, zadatek: event.target.value })); setModalFeedback(null) }} className="field mt-1.5" />
              </label>
              <label className="field-label sm:col-span-2">Notatka
                <textarea rows={3} value={modal.notatka || ''} disabled={!!modalAction} onChange={(event) => { setModal((current) => ({ ...current, notatka: event.target.value })); setModalFeedback(null) }} className="field mt-1.5 resize-y" />
              </label>
            </div>

            {modal.id && modal.email ? (
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

            <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
              {modal.id ? (
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

      {stolikModal ? (
        <DialogFrame title="Stoliki" closeLabel="Zamknij listę stolików" onClose={closeTables} restoreFocusRef={tableTriggerRef}>
          <div className="mb-5 space-y-2">
            {stoliki.length === 0 ? <p className="text-sm text-muted">Brak stolików. Dodaj pierwszy poniżej.</p> : null}
            {stoliki.map((table) => (
              <div key={table.id} className="border-b border-line py-2 last:border-0">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 text-sm text-ink">
                    <span className="font-semibold">{table.nazwa}</span>
                    {table.strefa ? <span className="text-muted"> · {table.strefa}</span> : null}
                    <span className="text-muted"> · {table.pojemnosc} os.</span>
                    {table.rewir_nr ? <span className="ml-2 rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-muted">POS {table.rewir_nr}</span> : null}
                  </div>
                  <Button
                    variant="subtle"
                    size="sm"
                    onClick={() => usunStolik(table)}
                    loading={tableActions[table.id] === 'delete'}
                    loadingLabel="Usuwam…"
                    disabled={!!tableActions[table.id]}
                    className="px-2 text-muted hover:text-danger"
                    aria-label={`Usuń stolik: ${table.nazwa}`}
                  >
                    <Icon name="trash" className="h-4 w-4" />
                  </Button>
                </div>
                <InlineFeedback feedback={tableRowFeedback[table.id]} className="mt-1 text-right" />
              </div>
            ))}
          </div>

          <form onSubmit={(event) => { event.preventDefault(); dodajStolik() }} className="border-t border-line pt-5">
            <h4 className="mb-4 text-sm font-semibold text-ink">Dodaj stolik</h4>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="field-label">Nazwa
                <input value={nowyStolik.nazwa} disabled={tableAdding} onChange={(event) => { setNowyStolik((current) => ({ ...current, nazwa: event.target.value })); setTableFeedback(null) }} className="field mt-1.5" placeholder="np. T4" />
              </label>
              <label className="field-label">Sala / strefa
                <input value={nowyStolik.strefa} disabled={tableAdding} onChange={(event) => { setNowyStolik((current) => ({ ...current, strefa: event.target.value })); setTableFeedback(null) }} list="strefy-lokalu" className="field mt-1.5" placeholder="np. Taras" />
                <datalist id="strefy-lokalu">{saleLokalu.map((room) => <option key={room} value={room} />)}</datalist>
              </label>
              <label className="field-label">Liczba miejsc
                <input type="number" min="1" value={nowyStolik.pojemnosc} disabled={tableAdding} onChange={(event) => { setNowyStolik((current) => ({ ...current, pojemnosc: event.target.value })); setTableFeedback(null) }} className="field mt-1.5" />
              </label>
              <label className="field-label">Rewir POS (opcjonalnie)
                <input type="number" min="1" value={nowyStolik.rewir_nr} disabled={tableAdding} onChange={(event) => { setNowyStolik((current) => ({ ...current, rewir_nr: event.target.value })); setTableFeedback(null) }} className="field mt-1.5" />
              </label>
            </div>
            <InlineFeedback pending={tableAdding ? 'Dodaję stolik…' : null} feedback={tableFeedback} className="mt-3" />
            <div className="mt-4 flex justify-end">
              <Button type="submit" size="sm" loading={tableAdding} loadingLabel="Dodaję…">
                <Icon name="plus" className="h-4 w-4" />
                {tableFeedback?.type === 'error' ? 'Ponów dodanie' : 'Dodaj stolik'}
              </Button>
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
              return (
                <div key={entry.id} className="border-b border-line py-3 last:border-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 text-sm text-ink">
                      <span className="font-semibold">{entry.nazwisko}</span>
                      {entry.godz_od ? ` · ${entry.godz_od}` : ''}
                      {entry.liczba_osob ? ` · ${entry.liczba_osob} os.` : ''}
                      {entry.telefon ? ` · ${entry.telefon}` : ''}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {entry.status !== 'oczekuje' ? (
                        <span className={`rounded-full px-2 py-1 text-xs ${entry.status === 'zrealizowany' ? 'bg-mint/15 text-mint' : 'bg-white/10 text-muted'}`}>
                          {entry.status === 'zrealizowany' ? 'Posadzony' : 'Odwołany'}
                        </span>
                      ) : null}
                      <Button
                        variant="subtle"
                        size="sm"
                        onClick={() => usunOczekujacego(entry)}
                        disabled={!!action}
                        loading={action === 'delete'}
                        loadingLabel="Usuwam…"
                        className="px-2 text-muted hover:text-danger"
                        aria-label={`Usuń z listy oczekujących: ${entry.nazwisko}`}
                      >
                        <Icon name="trash" className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  {entry.status === 'oczekuje' ? (
                    <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                      <label className="min-w-0 flex-1">
                        <span className="sr-only">Stolik dla {entry.nazwisko}</span>
                        <select
                          value={posadzStolik[entry.id] || ''}
                          onChange={(event) => {
                            setPosadzStolik((current) => ({ ...current, [entry.id]: event.target.value }))
                            setWaitRowFeedback((current) => ({ ...current, [entry.id]: null }))
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
                </div>
              )
            })}
          </div>

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
        </DialogFrame>
      ) : null}
    </Card>
  )
}
