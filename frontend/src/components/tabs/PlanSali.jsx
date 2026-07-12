import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { registerReservationLeaveGuard } from '../../lib/reservationLeaveGuard'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { useToast } from '../ui/Toast'

const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0))
const polishNoun = (value, one, few, many) => {
  const count = Math.abs(Number(value) || 0)
  const lastTwo = count % 100
  const last = count % 10
  if (count === 1) return one
  if (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) return few
  return many
}
const placesLabel = (value) => polishNoun(value, 'miejsce', 'miejsca', 'miejsc')
const roomsLabel = (value) => polishNoun(value, 'sala', 'sale', 'sal')
const tablesLabel = (value) => polishNoun(value, 'stół', 'stoły', 'stołów')
const rotatedHalfExtents = (width, height, rotation, canvas) => {
  const radians = (rotation * Math.PI) / 180
  const cosine = Math.abs(Math.cos(radians))
  const sine = Math.abs(Math.sin(radians))
  const canvasWidth = canvas?.clientWidth || 0
  const canvasHeight = canvas?.clientHeight || 0
  if (canvasWidth > 0 && canvasHeight > 0) {
    const widthPx = Math.max((width / 100) * canvasWidth, 44)
    const heightPx = Math.max((height / 100) * canvasHeight, 44)
    const halfWidthPx = ((widthPx * cosine) + (heightPx * sine)) / 2
    const halfHeightPx = ((widthPx * sine) + (heightPx * cosine)) / 2
    return {
      x: Number(((halfWidthPx / canvasWidth) * 100).toFixed(6)),
      y: Number(((halfHeightPx / canvasHeight) * 100).toFixed(6)),
    }
  }
  return {
    x: Number(((width * cosine + height * sine) / 2).toFixed(6)),
    y: Number(((width * sine + height * cosine) / 2).toFixed(6)),
  }
}
const geometry = (table, index = 0, count = 1) => {
  const columns = Math.max(1, Math.ceil(Math.sqrt(count * 1.6)))
  const rows = Math.max(1, Math.ceil(count / columns))
  const fallbackX = Math.round((((index % columns) + 0.5) / columns) * 84 + 8)
  const fallbackY = Math.round(((Math.floor(index / columns) + 0.5) / rows) * 84 + 8)
  return {
    plan_x: table.plan_x ?? fallbackX,
    plan_y: table.plan_y ?? fallbackY,
    szerokosc: table.szerokosc ?? 12,
    wysokosc: table.wysokosc ?? 12,
    obrot: table.obrot ?? 0,
    aktywny_w_planie: table.aktywny_w_planie ?? table.aktywny ?? true,
  }
}

const geometryMap = (tables = []) => Object.fromEntries(
  tables.map((table, index) => [table.id, geometry(table, index, tables.length)]),
)

const signature = (positions) => JSON.stringify(
  Object.entries(positions)
    .sort(([first], [second]) => Number(first) - Number(second))
    .map(([id, value]) => [Number(id), value]),
)

function RoomsSkeleton() {
  return (
    <div className="space-y-2" role="status" aria-label="Ładowanie sal">
      {[0, 1, 2].map((item) => (
        <div key={item} className="h-14 animate-pulse rounded-xl bg-white/[0.05] motion-reduce:animate-none" />
      ))}
    </div>
  )
}

function PlanSkeleton() {
  return (
    <div className="grid min-h-[420px] animate-pulse place-items-center rounded-2xl border border-line bg-white/[0.025] motion-reduce:animate-none" role="status">
      <span className="text-sm text-muted">Ładowanie planu…</span>
    </div>
  )
}

export default function PlanSali({ roomId, onRoomChange, active = true } = {}) {
  const { toast, confirm } = useToast()
  const [rooms, setRooms] = useState([])
  const [roomsLoading, setRoomsLoading] = useState(true)
  const [roomsError, setRoomsError] = useState(null)
  const [selectedRoomId, setSelectedRoomId] = useState(roomId || null)
  const [plan, setPlan] = useState(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [planError, setPlanError] = useState(null)
  const [mode, setMode] = useState('published')
  const [positions, setPositions] = useState({})
  const [selectedTableId, setSelectedTableId] = useState(null)
  const [busy, setBusy] = useState(null)
  const [conflict, setConflict] = useState(null)
  const [announcement, setAnnouncement] = useState('')
  const [addingRoom, setAddingRoom] = useState(false)
  const [newRoomName, setNewRoomName] = useState('')
  const [roomFeedback, setRoomFeedback] = useState(null)
  const [addingTable, setAddingTable] = useState(false)
  const [newTableName, setNewTableName] = useState('')
  const [newTableCapacity, setNewTableCapacity] = useState(2)
  const [tableFeedback, setTableFeedback] = useState(null)
  const roomsRequestRef = useRef(0)
  const planRequestRef = useRef(0)
  const selectedRoomIdRef = useRef(selectedRoomId)
  const readControllersRef = useRef(new Set())
  const mutationControllerRef = useRef(null)
  const baselineRef = useRef('{}')
  const positionsRef = useRef(positions)
  const planRef = useRef(plan)
  const modeRef = useRef(mode)
  const busyRef = useRef(busy)
  const canvasRef = useRef(null)
  const dragRef = useRef(null)
  positionsRef.current = positions
  planRef.current = plan
  modeRef.current = mode
  busyRef.current = busy
  selectedRoomIdRef.current = selectedRoomId

  const selectedRoom = useMemo(
    () => rooms.find((room) => room.id === selectedRoomId) || null,
    [rooms, selectedRoomId],
  )
  const tables = plan?.stoliki || []
  const selectedTable = useMemo(
    () => tables.find((table) => table.id === selectedTableId) || null,
    [selectedTableId, tables],
  )
  const dirty = mode === 'draft' && signature(positions) !== baselineRef.current
  const tableFormDirty = Boolean(
    mode === 'draft'
    && addingTable
    && (newTableName.trim() || Number(newTableCapacity) !== 2),
  )
  const roomFormDirty = Boolean(addingRoom && newRoomName.trim())
  const unsavedLocalChanges = dirty || tableFormDirty || roomFormDirty

  const cancelReads = useCallback(() => {
    roomsRequestRef.current += 1
    planRequestRef.current += 1
    readControllersRef.current.forEach((controller) => controller.abort())
    readControllersRef.current.clear()
  }, [])

  const cancelMutation = useCallback(() => {
    mutationControllerRef.current?.abort()
    mutationControllerRef.current = null
    setBusy(null)
  }, [])

  useEffect(() => {
    if (!unsavedLocalChanges) return undefined
    const warn = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsavedLocalChanges])

  useEffect(() => {
    if (!unsavedLocalChanges) return undefined
    return registerReservationLeaveGuard(() => confirm(
      'Wyjść z konfiguracji i odrzucić niezapisane zmiany lub wpisane dane?',
      {
        title: 'Niezapisany szkic',
        confirmText: 'Wyjdź bez zapisu',
        cancelText: 'Zostań tutaj',
      },
    ))
  }, [confirm, unsavedLocalChanges])

  useEffect(() => subscribeReservationPrivacyPurge(() => {
    cancelReads()
    cancelMutation()
    planRef.current = null
    setPlan(null)
    setPositions({})
    setSelectedTableId(null)
    setConflict(null)
    setAddingTable(false)
    setNewTableName('')
    setTableFeedback(null)
  }), [cancelMutation, cancelReads])

  useEffect(() => () => {
    cancelReads()
    cancelMutation()
  }, [cancelMutation, cancelReads])

  const installPlan = useCallback((response, nextMode) => {
    const nextPositions = geometryMap(response?.stoliki || [])
    planRef.current = response
    modeRef.current = nextMode
    setPlan(response)
    setPositions(nextPositions)
    positionsRef.current = nextPositions
    baselineRef.current = signature(nextPositions)
    setMode(nextMode)
    setSelectedTableId((current) => (
      response?.stoliki?.some((table) => table.id === current)
        ? current
        : response?.stoliki?.[0]?.id || null
    ))
    if (nextMode === 'published') setTableFeedback(null)
    setConflict(null)
    setPlanError(null)
  }, [])

  const loadRooms = useCallback(async ({ silent = false, preferredRoomId } = {}) => {
    if (!active) return null
    const controller = new AbortController()
    readControllersRef.current.add(controller)
    const requestId = ++roomsRequestRef.current
    if (!silent) setRoomsLoading(true)
    setRoomsError(null)
    try {
      const response = await api('/sale-rezerwacyjne', 'GET', null, { signal: controller.signal })
      if (controller.signal.aborted || requestId !== roomsRequestRef.current) return null
      const nextRooms = response.sale || []
      setRooms(nextRooms)
      const preferred = Number(
        preferredRoomId ?? roomId ?? selectedRoomIdRef.current,
      )
      const nextId = nextRooms.some((room) => room.id === preferred)
        ? preferred
        : nextRooms[0]?.id || null
      setSelectedRoomId(nextId)
      selectedRoomIdRef.current = nextId
      if (nextId !== roomId) onRoomChange?.(nextId)
      return { rooms: nextRooms, selectedRoomId: nextId }
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError' || requestId !== roomsRequestRef.current) return null
      setRoomsError(error.message || 'Nie udało się pobrać sal.')
      return null
    } finally {
      readControllersRef.current.delete(controller)
      if (!controller.signal.aborted && requestId === roomsRequestRef.current) setRoomsLoading(false)
    }
  }, [active, onRoomChange, roomId])

  const loadPublished = useCallback(async (nextRoomId = selectedRoomId) => {
    if (!active || !nextRoomId) {
      planRef.current = null
      setPlan(null)
      return null
    }
    const controller = new AbortController()
    readControllersRef.current.add(controller)
    const requestId = ++planRequestRef.current
    setPlanLoading(true)
    setPlanError(null)
    try {
      const response = await api(`/sale-rezerwacyjne/${nextRoomId}/plan`, 'GET', null, { signal: controller.signal })
      if (controller.signal.aborted || requestId !== planRequestRef.current) return null
      installPlan(response, 'published')
      return response
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError' || requestId !== planRequestRef.current) return null
      setPlanError({
        message: error.message || 'Nie udało się pobrać opublikowanego planu.',
        action: 'load',
      })
      // Przy odświeżaniu tej samej sali zachowujemy ostatni poprawny plan na ekranie.
      // Przełączenie sali czyści go wcześniej, więc nie grozi to pokazaniem obcego układu.
      if (Number(planRef.current?.sala?.id) !== Number(nextRoomId)) {
        planRef.current = null
        setPlan(null)
      }
      return null
    } finally {
      readControllersRef.current.delete(controller)
      if (!controller.signal.aborted && requestId === planRequestRef.current) setPlanLoading(false)
    }
  }, [active, installPlan, selectedRoomId])

  useEffect(() => {
    if (!active) {
      cancelReads()
      return
    }
    void loadRooms()
  }, [active, cancelReads, loadRooms])

  useEffect(() => {
    const normalized = Number(roomId) || null
    if (normalized && normalized !== selectedRoomId && rooms.some((room) => room.id === normalized)) {
      selectedRoomIdRef.current = normalized
      setSelectedRoomId(normalized)
    }
  }, [roomId, rooms, selectedRoomId])

  useEffect(() => {
    if (!active || !selectedRoomId) return
    if (
      modeRef.current === 'draft'
      && planRef.current?.sala?.id === selectedRoomId
    ) return
    void loadPublished(selectedRoomId)
  }, [active, loadPublished, selectedRoomId])

  const chooseRoom = async (nextRoomId) => {
    if (nextRoomId === selectedRoomId || busy) return
    if (dirty || tableFormDirty) {
      const discard = await confirm('Odrzucić niezapisane zmiany i wpisane dane tej sali?', {
        title: 'Niezapisany szkic',
        confirmText: 'Odrzuć zmiany',
        cancelText: 'Zostań tutaj',
      })
      if (!discard) return
    }
    cancelReads()
    cancelMutation()
    setSelectedRoomId(nextRoomId)
    selectedRoomIdRef.current = nextRoomId
    planRef.current = null
    modeRef.current = 'published'
    setPlan(null)
    setPositions({})
    setMode('published')
    setSelectedTableId(null)
    setAddingTable(false)
    setNewTableName('')
    setTableFeedback(null)
    onRoomChange?.(nextRoomId)
  }

  const createRoom = async (event) => {
    event.preventDefault()
    const name = newRoomName.trim()
    if (!name || busy) return
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy('room')
    setRoomFeedback(null)
    try {
      const created = await api('/sale-rezerwacyjne', 'POST', {
        nazwa: name,
        aktywna: true,
        kolejnosc: rooms.length,
      }, { signal: controller.signal })
      if (controller.signal.aborted) return
      setNewRoomName('')
      setAddingRoom(false)
      setRoomFeedback({ type: 'success', message: `Dodano salę „${created.nazwa}”.` })
      await loadRooms({ silent: true, preferredRoomId: created.id })
      if (controller.signal.aborted) return
      onRoomChange?.(created.id)
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      setRoomFeedback({ type: 'error', message: error.message || 'Nie udało się dodać sali.' })
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const createTable = async (event) => {
    event.preventDefault()
    const name = newTableName.trim()
    const capacity = Math.round(clamp(newTableCapacity, 1, 50))
    if (!name || !selectedRoomId || mode !== 'draft' || !plan?.wersja || busy) return
    let currentPlan = plan
    if (dirty) {
      currentPlan = await persistDraft({ quiet: true })
      if (!currentPlan) return
    }
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy('table')
    setTableFeedback(null)
    try {
      const previousIds = new Set(currentPlan.stoliki.map((table) => table.id))
      const response = await api(
        `/sale-rezerwacyjne/${selectedRoomId}/plan/szkic/stoliki`,
        'POST',
        {
          expected_revision: currentPlan.wersja.rewizja,
          nazwa: name,
          pojemnosc: capacity,
        },
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return
      const created = response.stoliki.find((table) => !previousIds.has(table.id))
      installPlan(response, 'draft')
      if (created) setSelectedTableId(created.id)
      setNewTableName('')
      setNewTableCapacity(2)
      setAddingTable(false)
      setTableFeedback({
        type: 'success',
        message: `Dodano „${created?.nazwa || name}” do szkicu. Stół zacznie działać po publikacji.`,
      })
      await loadRooms({ silent: true, preferredRoomId: selectedRoomId })
      if (controller.signal.aborted) return
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      if (error?.status === 409 && error?.code === 'PLAN_REVISION_CONFLICT') {
        setConflict('Ten szkic został zmieniony w innej karcie. Nazwa nowego stołu pozostała w formularzu; pobierz aktualny szkic i spróbuj ponownie.')
      } else {
        setTableFeedback({
          type: 'error',
          message: error.message || 'Nie udało się dodać stołu do szkicu.',
        })
      }
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const startDraft = async () => {
    if (!selectedRoomId || busy) return
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy('draft')
    setPlanError(null)
    try {
      const response = await api(
        `/sale-rezerwacyjne/${selectedRoomId}/plan/szkic`,
        'POST',
        {},
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return
      installPlan(response, 'draft')
      await loadRooms({ silent: true, preferredRoomId: selectedRoomId })
      if (controller.signal.aborted) return
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      setPlanError({
        message: error.message || 'Nie udało się rozpocząć szkicu.',
        action: 'draft',
      })
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const setTableGeometry = useCallback((tableId, patch) => {
    if (busyRef.current) return
    setPositions((current) => {
      const previous = current[tableId]
      if (!previous) return current
      const merged = { ...previous, ...patch }
      merged.szerokosc = Math.round(clamp(merged.szerokosc, 8, 32))
      merged.wysokosc = Math.round(clamp(merged.wysokosc, 8, 32))
      merged.obrot = ((Math.round(Number(merged.obrot) || 0) % 360) + 360) % 360
      const halfExtent = rotatedHalfExtents(
        merged.szerokosc,
        merged.wysokosc,
        merged.obrot,
        canvasRef.current,
      )
      merged.plan_x = clamp(
        Math.round(Number(merged.plan_x) || 0),
        Math.ceil(halfExtent.x),
        Math.floor(100 - halfExtent.x),
      )
      merged.plan_y = clamp(
        Math.round(Number(merged.plan_y) || 0),
        Math.ceil(halfExtent.y),
        Math.floor(100 - halfExtent.y),
      )
      return { ...current, [tableId]: merged }
    })
  }, [])

  const announcePosition = useCallback((tableId) => {
    const table = tables.find((item) => item.id === tableId)
    const next = positionsRef.current[tableId]
    if (table && next) setAnnouncement(`${table.nazwa}: X ${Math.round(next.plan_x)}%, Y ${Math.round(next.plan_y)}%.`)
  }, [tables])

  const onTableKeyDown = (event, tableId) => {
    if (mode !== 'draft' || busy || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
    event.preventDefault()
    const step = event.shiftKey ? 5 : 1
    const current = positionsRef.current[tableId]
    if (!current) return
    const patch = {
      plan_x: current.plan_x + (event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0),
      plan_y: current.plan_y + (event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0),
    }
    setTableGeometry(tableId, patch)
    queueMicrotask(() => announcePosition(tableId))
  }

  const onPointerDown = (event, tableId) => {
    setSelectedTableId(tableId)
    if (mode !== 'draft' || busy || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const current = positionsRef.current[tableId]
    if (!current) return
    try { event.currentTarget.setPointerCapture(event.pointerId) } catch { /* jsdom/Safari fallback */ }
    dragRef.current = {
      tableId,
      pointerId: event.pointerId,
      offsetX: ((event.clientX - rect.left) / rect.width) * 100 - current.plan_x,
      offsetY: ((event.clientY - rect.top) / rect.height) * 100 - current.plan_y,
    }
  }

  const onPointerMove = (event) => {
    const drag = dragRef.current
    const rect = canvasRef.current?.getBoundingClientRect()
    if (busy || !drag || !rect || drag.pointerId !== event.pointerId) return
    setTableGeometry(drag.tableId, {
      plan_x: ((event.clientX - rect.left) / rect.width) * 100 - drag.offsetX,
      plan_y: ((event.clientY - rect.top) / rect.height) * 100 - drag.offsetY,
    })
  }

  const endPointer = (event) => {
    const tableId = dragRef.current?.tableId
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null
    if (tableId) announcePosition(tableId)
  }

  const draftPayload = (expectedRevision) => ({
    expected_revision: expectedRevision,
    pozycje: tables.map((table) => ({
      stolik_id: table.id,
      ...positionsRef.current[table.id],
    })),
  })

  const persistDraft = async ({ quiet = false } = {}) => {
    if (mode !== 'draft' || !plan?.wersja || busy) return plan
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy('save')
    setConflict(null)
    setPlanError(null)
    try {
      const response = await api(
        `/sale-rezerwacyjne/${selectedRoomId}/plan/szkic`,
        'PUT',
        draftPayload(plan.wersja.rewizja),
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return null
      installPlan(response, 'draft')
      if (!quiet) toast('Szkic planu został zapisany.', 'success', { scope: 'reservations' })
      await loadRooms({ silent: true, preferredRoomId: selectedRoomId })
      if (controller.signal.aborted) return null
      return response
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return null
      if (error?.status === 409 && error?.code === 'PLAN_REVISION_CONFLICT') {
        setConflict('Ten szkic został zmieniony w innej karcie. Twoje lokalne ustawienie pozostało na ekranie.')
      } else if (error?.status === 422 && error?.code === 'PLAN_SNAPSHOT_INVALID') {
        setConflict('Lista stołów w tej sali zmieniła się w innej karcie. Lokalne ustawienie pozostało na ekranie; pobierz aktualny szkic, aby uzgodnić skład.')
      } else {
        setPlanError({
          message: error.message || 'Nie udało się zapisać szkicu.',
          action: 'save',
        })
      }
      return null
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const publishDraft = async () => {
    if (mode !== 'draft' || !plan?.wersja || busy) return
    if (tableFormDirty) {
      const publishWithoutTable = await confirm(
        'Opublikować plan bez dodawania stołu wpisanego w formularzu?',
        {
          title: 'Niedokończony stół',
          confirmText: 'Opublikuj bez stołu',
          cancelText: 'Wróć do formularza',
        },
      )
      if (!publishWithoutTable) return
      setAddingTable(false)
      setNewTableName('')
      setNewTableCapacity(2)
    }
    let current = plan
    if (dirty) {
      current = await persistDraft({ quiet: true })
      if (!current) return
    }
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy('publish')
    setConflict(null)
    setPlanError(null)
    try {
      const response = await api(
        `/sale-rezerwacyjne/${selectedRoomId}/plan/publikuj`,
        'POST',
        { expected_revision: current.wersja.rewizja },
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return
      installPlan(response, 'published')
      toast('Plan sali został opublikowany.', 'success', { scope: 'reservations' })
      await loadRooms({ silent: true, preferredRoomId: selectedRoomId })
      if (controller.signal.aborted) return
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      if (error?.status === 409 && error?.code === 'PLAN_REVISION_CONFLICT') {
        setConflict('Publikacja została zatrzymana, ponieważ szkic ma już nowszą wersję.')
      } else if (error?.status === 422 && error?.code === 'PLAN_SNAPSHOT_INVALID') {
        setConflict('Lista stołów w tej sali zmieniła się w innej karcie. Pobierz aktualny szkic, aby uzgodnić skład przed publikacją.')
      } else {
        setPlanError({
          message: error.message || 'Nie udało się opublikować planu.',
          action: 'publish',
        })
      }
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const discardDraft = async () => {
    if (mode !== 'draft' || !plan?.wersja || busy) return
    const discard = await confirm('Odrzucić szkic i wrócić do ostatniego opublikowanego planu?', {
      title: 'Odrzuć szkic',
      confirmText: 'Odrzuć szkic',
      cancelText: 'Zachowaj',
    })
    if (!discard) return
    const controller = new AbortController()
    mutationControllerRef.current = controller
    setBusy('discard')
    try {
      await api(
        `/sale-rezerwacyjne/${selectedRoomId}/plan/szkic?expected_revision=${plan.wersja.rewizja}`,
        'DELETE',
        null,
        { signal: controller.signal },
      )
      if (controller.signal.aborted) return
      modeRef.current = 'published'
      planRef.current = null
      setMode('published')
      setPlan(null)
      setPositions({})
      positionsRef.current = {}
      baselineRef.current = '{}'
      setSelectedTableId(null)
      setAddingTable(false)
      setTableFeedback(null)
      await loadPublished(selectedRoomId)
      if (controller.signal.aborted) return
      await loadRooms({ silent: true, preferredRoomId: selectedRoomId })
      if (controller.signal.aborted) return
      toast('Szkic został odrzucony.', 'success', { scope: 'reservations' })
    } catch (error) {
      if (controller.signal.aborted || error?.name === 'AbortError') return
      if (error?.status === 409 && error?.code === 'PLAN_REVISION_CONFLICT') {
        setConflict('Nie można odrzucić szkicu, ponieważ ma już nowszą wersję.')
      } else {
        setPlanError({
          message: error.message || 'Nie udało się odrzucić szkicu.',
          action: 'discard',
        })
      }
    } finally {
      if (mutationControllerRef.current === controller) mutationControllerRef.current = null
      if (!controller.signal.aborted) setBusy(null)
    }
  }

  const reloadConflict = async () => {
    if (dirty) {
      const discard = await confirm('Pobrać nowszy szkic i odrzucić lokalne zmiany?', {
        title: 'Nowsza wersja szkicu',
        confirmText: 'Pobierz nowszą',
        cancelText: 'Zachowaj lokalne',
      })
      if (!discard) return
    }
    await startDraft()
  }

  const retryPlanError = () => {
    if (planError?.action === 'save') return persistDraft()
    if (planError?.action === 'publish') return publishDraft()
    if (planError?.action === 'discard') return discardDraft()
    if (planError?.action === 'draft') return startDraft()
    return loadPublished()
  }

  if (roomsLoading && rooms.length === 0) {
    return <Card className="p-5 sm:p-7"><RoomsSkeleton /></Card>
  }

  if (roomsError && rooms.length === 0) {
    return (
      <Banner variant="danger">
        <div className="flex flex-wrap items-center gap-3">
          <span>{roomsError}</span>
          <Button variant="ghost" size="sm" onClick={() => loadRooms()}>Spróbuj ponownie</Button>
        </div>
      </Banner>
    )
  }

  return (
    <Card className="overflow-hidden">
      <div className="lg:grid lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="border-b border-line p-4 lg:border-b-0 lg:border-r lg:p-5" aria-label="Sale">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-ink">Sale</h3>
              <p className="mt-0.5 text-xs text-muted">{rooms.length} {roomsLabel(rooms.length)}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                if (addingRoom) {
                  setAddingRoom(false)
                  setNewRoomName('')
                } else {
                  setAddingRoom(true)
                }
                setRoomFeedback(null)
              }}
              disabled={Boolean(busy)}
              className="grid min-h-11 min-w-11 place-items-center rounded-xl text-muted transition hover:bg-white/[0.06] hover:text-ink"
              aria-label={addingRoom ? 'Anuluj dodawanie sali' : 'Dodaj salę'}
              aria-expanded={addingRoom}
            >
              <Icon name={addingRoom ? 'close' : 'plus'} className="h-4 w-4" />
            </button>
          </div>

          {addingRoom ? (
            <form onSubmit={createRoom} className="mt-4 space-y-2">
              <label className="field-label" htmlFor="new-room-name">Nazwa sali</label>
              <input
                id="new-room-name"
                autoFocus
                value={newRoomName}
                onChange={(event) => setNewRoomName(event.target.value)}
                className="field"
                maxLength={32}
                placeholder="np. Sala główna"
                disabled={Boolean(busy)}
              />
              <Button type="submit" size="sm" loading={busy === 'room'} loadingLabel="Dodaję…" disabled={Boolean(busy) || !newRoomName.trim()} className="w-full">
                Dodaj salę
              </Button>
            </form>
          ) : null}

          {roomFeedback ? (
            <p className={`mt-3 text-xs ${roomFeedback.type === 'error' ? 'text-danger' : 'text-success'}`} role={roomFeedback.type === 'error' ? 'alert' : 'status'}>
              {roomFeedback.message}
            </p>
          ) : null}

          {rooms.length ? (
            <div className="mt-4 flex gap-2 overflow-x-auto pb-1 lg:block lg:space-y-1 lg:overflow-visible" role="list">
              {rooms.map((room) => {
                const selected = room.id === selectedRoomId
                return (
                  <button
                    key={room.id}
                    type="button"
                    onClick={() => chooseRoom(room.id)}
                    disabled={Boolean(busy)}
                    aria-current={selected ? 'page' : undefined}
                    className={`min-h-12 min-w-[11rem] rounded-xl px-3 py-2 text-left transition disabled:cursor-wait disabled:opacity-60 lg:min-w-0 lg:w-full ${selected ? 'bg-mint/12 text-ink' : 'text-muted hover:bg-white/[0.05] hover:text-ink'}`}
                  >
                    <span className="block truncate text-sm font-semibold" title={room.nazwa}>{room.nazwa}</span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[0.7rem]">
                      {room.szkic ? `Szkic v${room.szkic.numer}` : room.wersja_opublikowana ? `Opublikowany v${room.wersja_opublikowana.numer}` : 'Bez planu'}
                      <span aria-hidden>·</span>
                      {room.liczba_stolikow || 0} {tablesLabel(room.liczba_stolikow || 0)}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="mt-5 rounded-xl border border-dashed border-line px-3 py-5 text-center">
              <p className="text-sm font-medium text-ink">Dodaj pierwszą salę</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">Każda sala otrzyma osobny, publikowany plan.</p>
            </div>
          )}
        </aside>

        <div className="min-w-0 p-4 sm:p-6 lg:p-7">
          {!selectedRoom ? (
            <div className="grid min-h-[420px] place-items-center text-center">
              <div className="max-w-sm">
                <Icon name="office" className="mx-auto h-8 w-8 text-muted" />
                <h3 className="mt-4 text-lg font-semibold text-ink">Najpierw dodaj salę</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">Szkice oddzielają przygotowywany układ od planu używanego podczas pracy.</p>
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate font-display text-xl font-semibold text-ink" title={selectedRoom.nazwa}>{selectedRoom.nazwa}</h3>
                    {plan?.wersja ? (
                      <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${mode === 'draft' ? 'border-lemon/30 bg-lemon/10 text-lemon' : 'border-success/30 bg-success/10 text-success'}`}>
                        {mode === 'draft' ? `Szkic v${plan.wersja.numer}` : `Opublikowany v${plan.wersja.numer}`}
                      </span>
                    ) : (
                      <span className="rounded-full border border-line bg-white/[0.04] px-2.5 py-1 text-xs font-semibold text-muted">Bez publikacji</span>
                    )}
                    {dirty ? <span className="text-xs font-medium text-lemon">Niezapisane zmiany</span> : null}
                  </div>
                  <p className="mt-1 text-sm text-muted">
                    {mode === 'draft' ? 'Zmiany są widoczne tylko tutaj do czasu publikacji.' : 'To jest układ używany przez obsługę.'}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {mode === 'published' ? (
                    <Button variant="primary" size="sm" onClick={startDraft} loading={busy === 'draft'} loadingLabel="Otwieram…" disabled={Boolean(busy)}>
                      {selectedRoom.szkic ? 'Otwórz szkic' : 'Edytuj jako szkic'}
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          if (addingTable) {
                            setAddingTable(false)
                            setNewTableName('')
                            setNewTableCapacity(2)
                          } else {
                            setAddingTable(true)
                          }
                          setTableFeedback(null)
                        }}
                        disabled={Boolean(busy)}
                      >
                        {addingTable ? 'Anuluj dodawanie' : 'Dodaj stół'}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={discardDraft} loading={busy === 'discard'} loadingLabel="Odrzucam…" disabled={Boolean(busy)}>Odrzuć</Button>
                      <Button variant="ghost" size="sm" onClick={() => persistDraft()} loading={busy === 'save'} loadingLabel="Zapisuję…" disabled={Boolean(busy) || !dirty}>Zapisz szkic</Button>
                      <Button variant="primary" size="sm" onClick={publishDraft} loading={busy === 'publish'} loadingLabel="Publikuję…" disabled={Boolean(busy)}>Opublikuj</Button>
                    </>
                  )}
                </div>
              </div>

              {addingTable && mode === 'draft' ? (
                <form onSubmit={createTable} className="mt-5 grid gap-3 rounded-xl border border-line bg-white/[0.025] p-4 sm:grid-cols-[minmax(0,1fr)_8rem_auto] sm:items-end">
                  <label className="field-label">
                    Nazwa stołu
                    <input
                      autoFocus
                      value={newTableName}
                      onChange={(event) => setNewTableName(event.target.value)}
                      className="field mt-1.5"
                      maxLength={32}
                      placeholder="np. S1"
                      disabled={Boolean(busy)}
                    />
                  </label>
                  <label className="field-label">
                    Liczba miejsc
                    <input
                      type="number"
                      min="1"
                      max="50"
                      value={newTableCapacity}
                      onChange={(event) => setNewTableCapacity(event.target.value)}
                      className="field mt-1.5"
                      disabled={Boolean(busy)}
                    />
                  </label>
                  <Button type="submit" size="sm" loading={busy === 'table'} loadingLabel="Dodaję…" disabled={Boolean(busy) || !newTableName.trim()}>
                    Dodaj do szkicu
                  </Button>
                  <p className="text-xs leading-relaxed text-muted sm:col-span-3">Nowy stół nie trafi do bieżących rezerwacji, dopóki nie opublikujesz planu.</p>
                </form>
              ) : null}

              {tableFeedback ? (
                <p className={`mt-3 text-xs ${tableFeedback.type === 'error' ? 'text-danger' : 'text-success'}`} role={tableFeedback.type === 'error' ? 'alert' : 'status'}>
                  {tableFeedback.message}
                </p>
              ) : null}

              {roomsError ? <p className="mt-4 text-xs text-lemon" role="status">Lista sal nie odświeżyła się: {roomsError}</p> : null}
              {planError ? (
                <div className="mt-4" role="alert">
                  <Banner variant="danger">
                    <div className="flex flex-wrap items-center gap-3">
                      <span>{planError.message}</span>
                      <Button variant="ghost" size="sm" onClick={retryPlanError}>Spróbuj ponownie</Button>
                    </div>
                  </Banner>
                </div>
              ) : null}
              {conflict ? (
                <div className="mt-4" role="alert">
                  <Banner variant="warn">
                    <div className="flex flex-wrap items-center gap-3">
                      <span>{conflict}</span>
                      <Button variant="ghost" size="sm" onClick={reloadConflict}>Pobierz nowszą wersję</Button>
                    </div>
                  </Banner>
                </div>
              ) : null}

              <div className="mt-5">
                {planLoading && !plan ? (
                  <PlanSkeleton />
                ) : tables.length === 0 ? (
                  <div className="grid min-h-[420px] place-items-center rounded-2xl border border-dashed border-line bg-white/[0.015] px-6 text-center">
                    <div className="max-w-md">
                      <h4 className="text-base font-semibold text-ink">Ta sala nie ma jeszcze stołów</h4>
                      <p className="mt-2 text-sm leading-relaxed text-muted">
                        {mode === 'draft' ? 'Użyj przycisku „Dodaj stół” powyżej. Zmiana zacznie działać dopiero po publikacji.' : 'Otwórz szkic, aby dodać pierwszy stół bez wpływu na bieżącą pracę obsługi.'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="xl:grid xl:grid-cols-[minmax(0,1fr)_18rem]">
                    <div className="min-w-0">
                      <div className="overflow-x-auto pb-2">
                        <div
                          ref={canvasRef}
                          onPointerMove={onPointerMove}
                          onPointerUp={endPointer}
                          onPointerCancel={endPointer}
                          className="relative aspect-[4/3] w-full min-w-[46rem] overflow-hidden rounded-2xl border border-white/[0.10] bg-surface"
                          style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.07) 1px, transparent 1px)', backgroundSize: '24px 24px' }}
                          aria-label={`Plan: ${selectedRoom.nazwa}`}
                        >
                        {tables.map((table) => {
                          const value = positions[table.id] || geometry(table)
                          const selected = table.id === selectedTableId
                          return (
                            <button
                              key={table.id}
                              type="button"
                              onPointerDown={(event) => onPointerDown(event, table.id)}
                              onKeyDown={(event) => onTableKeyDown(event, table.id)}
                              onClick={() => setSelectedTableId(table.id)}
                              disabled={Boolean(busy)}
                              aria-pressed={selected}
                              aria-label={`${table.nazwa}, ${table.pojemnosc} ${placesLabel(table.pojemnosc)}, ${value.aktywny_w_planie ? 'aktywny w planie' : 'nieaktywny w planie'}, pozycja X ${Math.round(value.plan_x)}%, Y ${Math.round(value.plan_y)}%`}
                              className={`absolute grid min-h-11 min-w-11 place-items-center rounded-xl border text-center transition-[border-color,background-color,box-shadow] duration-150 ${value.aktywny_w_planie ? 'border-white/[0.16] bg-surface-2 text-ink' : 'border-line bg-bg/80 text-muted'} ${selected ? 'ring-2 ring-mint ring-offset-2 ring-offset-bg' : 'hover:border-white/[0.24]'} ${busy ? 'cursor-wait' : mode === 'draft' ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'}`}
                              style={{
                                left: `${value.plan_x}%`,
                                top: `${value.plan_y}%`,
                                width: `${value.szerokosc}%`,
                                height: `${value.wysokosc}%`,
                                transform: `translate(-50%, -50%) rotate(${value.obrot}deg)`,
                                touchAction: mode === 'draft' && !busy ? 'none' : 'manipulation',
                              }}
                            >
                              <span style={{ transform: `rotate(${-value.obrot}deg)` }}>
                                <span className="block max-w-[8rem] truncate px-1 text-xs font-semibold">{table.nazwa}</span>
                                <span className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted"><Icon name="users" className="h-3 w-3" />{table.pojemnosc}</span>
                              </span>
                            </button>
                          )
                        })}
                        </div>
                      </div>
                      <p className="mt-3 text-xs leading-relaxed text-muted">
                        {mode === 'draft' ? 'Przeciągnij stół albo zaznacz go i użyj strzałek. Shift + strzałka przesuwa o 5%. Na małym ekranie przesuń cały plan w bok.' : 'Wybierz stół, aby zobaczyć jego pozycję i rozmiar. Na małym ekranie przesuń cały plan w bok.'}
                      </p>
                    </div>

                    <aside className="mt-5 border-t border-line pt-5 xl:mt-0 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0" aria-label="Właściwości stołu">
                      {selectedTable ? (
                        <div>
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h4 className="truncate text-base font-semibold text-ink" title={selectedTable.nazwa}>{selectedTable.nazwa}</h4>
                              <p className="mt-1 text-xs text-muted">{selectedTable.pojemnosc} {placesLabel(selectedTable.pojemnosc)} · stabilny stół #{selectedTable.id}</p>
                            </div>
                            <span className={`rounded-full px-2 py-1 text-[0.68rem] font-semibold ${positions[selectedTable.id]?.aktywny_w_planie ? 'bg-success/10 text-success' : 'bg-white/[0.05] text-muted'}`}>
                              {positions[selectedTable.id]?.aktywny_w_planie ? 'Aktywny' : 'Nieaktywny'}
                            </span>
                          </div>

                          <div className="mt-5 grid grid-cols-2 gap-3">
                            {[
                              ['plan_x', 'Pozycja X', 0, 100],
                              ['plan_y', 'Pozycja Y', 0, 100],
                              ['szerokosc', 'Szerokość', 8, 32],
                              ['wysokosc', 'Wysokość', 8, 32],
                              ['obrot', 'Obrót', 0, 359],
                            ].map(([field, label, min, max]) => (
                              <label key={field} className={field === 'obrot' ? 'col-span-2 field-label' : 'field-label'}>
                                {label}
                                <span className="relative mt-1.5 block">
                                  <input
                                    type="number"
                                    min={min}
                                    max={max}
                                    value={Math.round(positions[selectedTable.id]?.[field] ?? 0)}
                                    onChange={(event) => setTableGeometry(selectedTable.id, { [field]: Number(event.target.value) })}
                                    disabled={mode !== 'draft' || Boolean(busy)}
                                    className="field pr-8 normal-case tracking-normal"
                                    aria-label={`${label} stołu ${selectedTable.nazwa}`}
                                  />
                                  <span className="pointer-events-none absolute inset-y-0 right-3 grid place-items-center text-xs font-normal text-muted">{field === 'obrot' ? '°' : '%'}</span>
                                </span>
                              </label>
                            ))}
                          </div>

                          <label className="mt-4 flex min-h-11 items-center justify-between gap-4 rounded-xl border border-line bg-white/[0.025] px-3 py-2 text-sm text-ink">
                            <span>
                              <span className="block font-medium">Aktywny w planie</span>
                              <span className="mt-0.5 block text-xs text-muted">Wyłączenie wymaga publikacji i braku przyszłych rezerwacji.</span>
                            </span>
                            <input
                              type="checkbox"
                              checked={Boolean(positions[selectedTable.id]?.aktywny_w_planie)}
                              onChange={(event) => setTableGeometry(selectedTable.id, { aktywny_w_planie: event.target.checked })}
                              disabled={mode !== 'draft' || Boolean(busy)}
                              className="h-5 w-5 accent-mint"
                            />
                          </label>
                        </div>
                      ) : (
                        <div className="py-8 text-center text-sm text-muted">Wybierz stół na planie.</div>
                      )}
                    </aside>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
      <p className="sr-only" aria-live="polite">{announcement}</p>
    </Card>
  )
}
