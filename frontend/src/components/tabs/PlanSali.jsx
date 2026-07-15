import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { Icon } from '../../lib/icons'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { registerReservationLeaveGuard } from '../../lib/reservationLeaveGuard'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { PillSwitch } from '../ui/PillSwitch'
import { useToast } from '../ui/Toast'
import {
  cloneEditorSnapshot,
  combinationCapacityBreakdown,
  combinationKey,
  edgeKey,
  editorSignature,
  findStructuralSeating,
  isConnectedSet,
  neighborIds,
  normalizeCombinations,
  normalizeEdges,
  proposeConnectedCombinations,
} from './floorPlanEditor'

const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0))
const positiveInteger = (value, fallback = 1) => {
  const parsed = Math.round(Number(value))
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : fallback
}
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
    nazwa: table.nazwa ?? `Stół ${index + 1}`,
    kolejnosc: table.kolejnosc ?? index,
    pojemnosc: table.pojemnosc ?? 2,
    pojemnosc_min: table.pojemnosc_min ?? 1,
    ksztalt: table.ksztalt ?? null,
    cechy: Array.isArray(table.cechy) ? [...table.cechy] : [],
    priorytet: table.priorytet ?? 0,
    sekcja: table.sekcja ?? null,
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
  const [edges, setEdges] = useState([])
  const [combinations, setCombinations] = useState([])
  const [editorTool, setEditorTool] = useState('layout')
  const [connectionStartId, setConnectionStartId] = useState(null)
  const [connectionTargetId, setConnectionTargetId] = useState('')
  const [connectionFeedback, setConnectionFeedback] = useState(null)
  const [history, setHistory] = useState({ past: [], future: [] })
  const [featureDrafts, setFeatureDrafts] = useState({})
  const [checkerPeople, setCheckerPeople] = useState(18)
  const [checkerChannel, setCheckerChannel] = useState('wewnetrzna')
  const [checkerResult, setCheckerResult] = useState(null)
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
  const baselineRef = useRef(editorSignature({}, [], []))
  const positionsRef = useRef(positions)
  const edgesRef = useRef(edges)
  const combinationsRef = useRef(combinations)
  const historyRef = useRef(history)
  const planRef = useRef(plan)
  const modeRef = useRef(mode)
  const busyRef = useRef(busy)
  const canvasRef = useRef(null)
  const dragRef = useRef(null)
  positionsRef.current = positions
  edgesRef.current = edges
  combinationsRef.current = combinations
  historyRef.current = history
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
  const selectedProperties = selectedTable
    ? positions[selectedTable.id] || geometry(selectedTable)
    : null
  const selectedNeighborIds = useMemo(
    () => neighborIds(selectedTableId, edges),
    [edges, selectedTableId],
  )
  const selectedNeighbors = useMemo(
    () => selectedNeighborIds.map((id) => {
      const table = tables.find((item) => item.id === id)
      return table ? { ...table, ...positions[id] } : null
    }).filter(Boolean),
    [positions, selectedNeighborIds, tables],
  )
  const activeTables = useMemo(
    () => tables
      .filter((table) => positions[table.id]?.aktywny_w_planie !== false)
      .map((table) => ({ ...table, ...positions[table.id] })),
    [positions, tables],
  )
  const proposalFocusTable = useMemo(
    () => activeTables.find((table) => table.id === selectedTableId) || null,
    [activeTables, selectedTableId],
  )
  const proposedCombinations = useMemo(
    () => proposalFocusTable
      ? proposeConnectedCombinations(activeTables, edges, combinations, {
        focusTableId: proposalFocusTable.id,
      })
      : [],
    [activeTables, combinations, edges, proposalFocusTable],
  )
  const dirty = mode === 'draft'
    && editorSignature(positions, edges, combinations) !== baselineRef.current
  const invalidTableProperties = mode === 'draft'
    ? tables.find((table) => !String(positions[table.id]?.nazwa || '').trim()) || null
    : null
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
    positionsRef.current = {}
    setEdges([])
    edgesRef.current = []
    setCombinations([])
    combinationsRef.current = []
    setHistory({ past: [], future: [] })
    historyRef.current = { past: [], future: [] }
    setFeatureDrafts({})
    baselineRef.current = editorSignature({}, [], [])
    modeRef.current = 'published'
    setMode('published')
    setEditorTool('layout')
    setConnectionStartId(null)
    setConnectionTargetId('')
    setConnectionFeedback(null)
    setCheckerResult(null)
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
    const nextEdges = normalizeEdges(response?.krawedzie || [])
    const nextCombinations = normalizeCombinations(response?.kombinacje || [])
    planRef.current = response
    modeRef.current = nextMode
    setPlan(response)
    setPositions(nextPositions)
    positionsRef.current = nextPositions
    setEdges(nextEdges)
    edgesRef.current = nextEdges
    setCombinations(nextCombinations)
    combinationsRef.current = nextCombinations
    setFeatureDrafts(Object.fromEntries(
      Object.entries(nextPositions).map(([id, value]) => [id, (value.cechy || []).join(', ')]),
    ))
    baselineRef.current = editorSignature(nextPositions, nextEdges, nextCombinations)
    const emptyHistory = { past: [], future: [] }
    setHistory(emptyHistory)
    historyRef.current = emptyHistory
    setMode(nextMode)
    setSelectedTableId((current) => (
      response?.stoliki?.some((table) => table.id === current)
        ? current
        : response?.stoliki?.[0]?.id || null
    ))
    if (nextMode === 'published') setTableFeedback(null)
    setEditorTool('layout')
    setConnectionStartId(null)
    setConnectionTargetId('')
    setConnectionFeedback(null)
    setCheckerResult(null)
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
    positionsRef.current = {}
    setEdges([])
    edgesRef.current = []
    setCombinations([])
    combinationsRef.current = []
    const emptyHistory = { past: [], future: [] }
    setHistory(emptyHistory)
    historyRef.current = emptyHistory
    setFeatureDrafts({})
    setMode('published')
    setEditorTool('layout')
    setConnectionStartId(null)
    setConnectionTargetId('')
    setConnectionFeedback(null)
    setCheckerResult(null)
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
    if (dirty || tableFormDirty) {
      const discard = await confirm('Dodać nową salę i odrzucić niezapisane zmiany tej sali?', {
        title: 'Niezapisany szkic',
        confirmText: 'Dodaj i odrzuć zmiany',
        cancelText: 'Zostań tutaj',
      })
      if (!discard) return
    }
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
    const capacity = positiveInteger(newTableCapacity, 2)
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

  const currentEditorSnapshot = useCallback(() => cloneEditorSnapshot(
    positionsRef.current,
    edgesRef.current,
    combinationsRef.current,
  ), [])

  const applyEditorSnapshot = useCallback((snapshot) => {
    const next = cloneEditorSnapshot(snapshot.positions, snapshot.edges, snapshot.combinations)
    positionsRef.current = next.positions
    edgesRef.current = next.edges
    combinationsRef.current = next.combinations
    setPositions(next.positions)
    setEdges(next.edges)
    setCombinations(next.combinations)
    setFeatureDrafts(Object.fromEntries(
      Object.entries(next.positions).map(([id, value]) => [id, (value.cechy || []).join(', ')]),
    ))
    setConnectionStartId(null)
    setConnectionTargetId('')
    setConnectionFeedback(null)
    setCheckerResult(null)
  }, [])

  const pushHistory = useCallback((snapshot) => {
    const nextHistory = {
      past: [...historyRef.current.past, snapshot].slice(-50),
      future: [],
    }
    historyRef.current = nextHistory
    setHistory(nextHistory)
  }, [])

  const undoEditor = useCallback(() => {
    if (modeRef.current !== 'draft' || busyRef.current || historyRef.current.past.length === 0) return
    const previous = historyRef.current.past.at(-1)
    const nextHistory = {
      past: historyRef.current.past.slice(0, -1),
      future: [currentEditorSnapshot(), ...historyRef.current.future].slice(0, 50),
    }
    historyRef.current = nextHistory
    setHistory(nextHistory)
    applyEditorSnapshot(previous)
    setAnnouncement('Cofnięto ostatnią zmianę planu.')
  }, [applyEditorSnapshot, currentEditorSnapshot])

  const redoEditor = useCallback(() => {
    if (modeRef.current !== 'draft' || busyRef.current || historyRef.current.future.length === 0) return
    const nextSnapshot = historyRef.current.future[0]
    const nextHistory = {
      past: [...historyRef.current.past, currentEditorSnapshot()].slice(-50),
      future: historyRef.current.future.slice(1),
    }
    historyRef.current = nextHistory
    setHistory(nextHistory)
    applyEditorSnapshot(nextSnapshot)
    setAnnouncement('Ponowiono ostatnią zmianę planu.')
  }, [applyEditorSnapshot, currentEditorSnapshot])

  const handleEditorShortcut = (event) => {
    if (mode !== 'draft' || busy) return
    if (event.key === 'Escape' && connectionStartId) {
      event.preventDefault()
      setConnectionStartId(null)
      setAnnouncement('Anulowano wybór pierwszego stołu.')
      return
    }
    const textEntry = event.target instanceof HTMLElement
      && (event.target.matches('input:not([data-editor-history]), textarea, [contenteditable="true"]'))
    if (textEntry || !(event.ctrlKey || event.metaKey)) return
    if (event.key.toLowerCase() === 'z' && event.shiftKey) {
      event.preventDefault()
      redoEditor()
    } else if (event.key.toLowerCase() === 'z') {
      event.preventDefault()
      undoEditor()
    } else if (event.key.toLowerCase() === 'y') {
      event.preventDefault()
      redoEditor()
    }
  }

  const setTableGeometry = useCallback((tableId, patch, { record = true } = {}) => {
    if (busyRef.current) return
    if (patch.aktywny_w_planie === false) {
      const activeCombination = combinationsRef.current.find((combination) => (
        combination.aktywna_w_planie && combination.stoliki.includes(Number(tableId))
      ))
      if (activeCombination) {
        setPlanError({
          message: `Stół należy do zestawu „${activeCombination.nazwa}”. Najpierw usuń ten zestaw.`,
          action: null,
        })
        return
      }
    }
    const current = positionsRef.current
    const previous = current[tableId]
    if (!previous) return
    const merged = { ...previous, ...patch }
    merged.nazwa = String(merged.nazwa ?? '').slice(0, 32)
    merged.kolejnosc = Math.max(0, Math.round(Number(merged.kolejnosc) || 0))
    merged.pojemnosc = positiveInteger(
      merged.pojemnosc,
      positiveInteger(previous.pojemnosc, 1),
    )
    merged.pojemnosc_min = Math.round(clamp(merged.pojemnosc_min, 1, merged.pojemnosc))
    merged.ksztalt = String(merged.ksztalt || '').trim().slice(0, 16) || null
    merged.cechy = [...new Set((Array.isArray(merged.cechy) ? merged.cechy : [])
      .map((item) => String(item).trim())
      .filter(Boolean))]
    merged.priorytet = Math.round(Number(merged.priorytet) || 0)
    merged.sekcja = String(merged.sekcja || '').slice(0, 32) || null
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
    if (JSON.stringify(previous) === JSON.stringify(merged)) return
    let nextCombinations = combinationsRef.current
    let combinationsAdjusted = false
    if (Object.prototype.hasOwnProperty.call(patch, 'pojemnosc')) {
      nextCombinations = normalizeCombinations(combinationsRef.current.map((combination) => {
        if (!combination.stoliki.includes(Number(tableId))) return combination
        const physicalCapacity = combination.stoliki.reduce((sum, memberId) => (
          sum + Number(memberId === Number(tableId)
            ? merged.pojemnosc
            : current[memberId]?.pojemnosc || 0)
        ), 0)
        const maximum = Math.min(combination.pojemnosc_max, physicalCapacity)
        const minimum = Math.min(combination.pojemnosc_min, maximum)
        if (maximum !== combination.pojemnosc_max || minimum !== combination.pojemnosc_min) {
          combinationsAdjusted = true
        }
        return {
          ...combination,
          pojemnosc_max: maximum,
          pojemnosc_min: minimum,
        }
      }))
    }
    if (record) pushHistory(currentEditorSnapshot())
    const nextPositions = { ...current, [tableId]: merged }
    positionsRef.current = nextPositions
    setPositions(nextPositions)
    setPlanError((currentError) => currentError?.action === null ? null : currentError)
    if (combinationsAdjusted) {
      combinationsRef.current = nextCombinations
      setCombinations(nextCombinations)
      setTableFeedback({ type: 'success', message: 'Dostosowano zakres zatwierdzonego zestawu do nowej liczby miejsc.' })
    }
    setCheckerResult(null)
  }, [currentEditorSnapshot, pushHistory])

  const announcePosition = useCallback((tableId) => {
    const table = tables.find((item) => item.id === tableId)
    const next = positionsRef.current[tableId]
    if (table && next) setAnnouncement(`${table.nazwa}: X ${Math.round(next.plan_x)}%, Y ${Math.round(next.plan_y)}%.`)
  }, [tables])

  const nameForTable = (tableId) => positionsRef.current[Number(tableId)]?.nazwa
    || tables.find((table) => table.id === Number(tableId))?.nazwa
    || `Stół ${tableId}`

  const toggleEdge = (firstId, secondId) => {
    if (mode !== 'draft' || busy) return false
    const key = edgeKey(firstId, secondId)
    if (!key) return false
    const exists = edgesRef.current.some((edge) => edgeKey(edge.stolik_a_id, edge.stolik_b_id) === key)
    const [stolikA, stolikB] = key.split(':').map(Number)
    const nextEdges = exists
      ? edgesRef.current.filter((edge) => edgeKey(edge.stolik_a_id, edge.stolik_b_id) !== key)
      : normalizeEdges([...edgesRef.current, { stolik_a_id: stolikA, stolik_b_id: stolikB }])
    if (exists) {
      const disconnected = combinationsRef.current.find((combination) => (
        !isConnectedSet(combination.stoliki, nextEdges)
      ))
      if (disconnected) {
        setConnectionFeedback({
          type: 'error',
          message: `Połączenie należy do zdefiniowanego zestawu „${disconnected.nazwa}”. Najpierw usuń ten zestaw.`,
        })
        return false
      }
    }
    pushHistory(currentEditorSnapshot())
    edgesRef.current = nextEdges
    setEdges(nextEdges)
    setConnectionFeedback({
      type: 'success',
      message: exists
        ? `Usunięto połączenie ${nameForTable(stolikA)} – ${nameForTable(stolikB)}.`
        : `Połączono ${nameForTable(stolikA)} i ${nameForTable(stolikB)}.`,
    })
    setCheckerResult(null)
    return true
  }

  const handleTableClick = (tableId) => {
    setSelectedTableId(tableId)
    if (mode !== 'draft' || editorTool !== 'connect' || busy) return
    if (!connectionStartId) {
      setConnectionStartId(tableId)
      setConnectionFeedback(null)
      setAnnouncement(`${nameForTable(tableId)} wybrany. Wybierz sąsiedni stół.`)
      return
    }
    if (connectionStartId === tableId) {
      setConnectionStartId(null)
      setAnnouncement('Anulowano wybór pierwszego stołu.')
      return
    }
    if (toggleEdge(connectionStartId, tableId)) setConnectionStartId(null)
  }

  const addTextConnection = (event) => {
    event.preventDefault()
    if (!selectedTableId || !connectionTargetId) return
    if (toggleEdge(selectedTableId, Number(connectionTargetId))) setConnectionTargetId('')
  }

  const approveCombination = (proposal) => {
    if (mode !== 'draft' || busy) return
    pushHistory(currentEditorSnapshot())
    const nextCombinations = normalizeCombinations([...combinationsRef.current, proposal])
    combinationsRef.current = nextCombinations
    setCombinations(nextCombinations)
    setConnectionFeedback({ type: 'success', message: `Zatwierdzono zestaw „${proposal.nazwa}”.` })
    setCheckerResult(null)
  }

  const updateCombination = (key, patch) => {
    if (mode !== 'draft' || busy) return
    const current = combinationsRef.current
    const index = current.findIndex((combination) => combinationKey(combination) === key)
    if (index < 0) return
    const updated = { ...current[index], ...patch }
    const physicalCapacity = updated.stoliki.reduce((sum, tableId) => (
      sum + Number(positionsRef.current[tableId]?.pojemnosc || 0)
    ), 0)
    if (patch.pojemnosc_min != null) {
      updated.pojemnosc_min = Math.max(
        1,
        Math.min(Number(patch.pojemnosc_min) || 1, updated.pojemnosc_max, physicalCapacity),
      )
    }
    if (patch.pojemnosc_max != null) {
      updated.pojemnosc_max = Math.max(
        updated.pojemnosc_min,
        Math.min(Number(patch.pojemnosc_max) || updated.pojemnosc_min, physicalCapacity),
      )
    }
    const nextCombinations = normalizeCombinations(current.map((combination, itemIndex) => (
      itemIndex === index ? updated : combination
    )))
    if (editorSignature(positionsRef.current, edgesRef.current, current)
      === editorSignature(positionsRef.current, edgesRef.current, nextCombinations)) return
    pushHistory(currentEditorSnapshot())
    combinationsRef.current = nextCombinations
    setCombinations(nextCombinations)
    setCheckerResult(null)
  }

  const removeCombination = (key) => {
    if (mode !== 'draft' || busy) return
    const combination = combinationsRef.current.find((item) => combinationKey(item) === key)
    if (!combination) return
    pushHistory(currentEditorSnapshot())
    const nextCombinations = combinationsRef.current.filter((item) => combinationKey(item) !== key)
    combinationsRef.current = nextCombinations
    setCombinations(nextCombinations)
    setConnectionFeedback({ type: 'success', message: `Usunięto zestaw „${combination.nazwa}” ze szkicu.` })
    setCheckerResult(null)
  }

  const checkStructure = (event) => {
    event.preventDefault()
    const people = positiveInteger(checkerPeople, 18)
    const activeIds = new Set(activeTables.map((table) => table.id))
    const activeCombinations = combinations.filter((combination) => (
      combination.stoliki.every((tableId) => activeIds.has(tableId))
    ))
    setCheckerPeople(people)
    setCheckerResult({
      people,
      match: findStructuralSeating(activeTables, activeCombinations, people, {
        channel: checkerChannel,
      }),
    })
  }

  const onTableKeyDown = (event, tableId) => {
    if (mode !== 'draft' || editorTool !== 'layout' || busy || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
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
    if (mode !== 'draft' || editorTool !== 'layout' || busy || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const current = positionsRef.current[tableId]
    if (!current) return
    try { event.currentTarget.setPointerCapture(event.pointerId) } catch { /* jsdom/Safari fallback */ }
    dragRef.current = {
      tableId,
      pointerId: event.pointerId,
      snapshot: currentEditorSnapshot(),
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
    }, { record: false })
  }

  const endPointer = (event) => {
    const drag = dragRef.current
    const tableId = drag?.tableId
    if (drag?.pointerId === event.pointerId) {
      dragRef.current = null
      if (drag.snapshot && editorSignature(drag.snapshot.positions, drag.snapshot.edges, drag.snapshot.combinations)
        !== editorSignature(positionsRef.current, edgesRef.current, combinationsRef.current)) {
        pushHistory(drag.snapshot)
      }
    }
    if (tableId) announcePosition(tableId)
  }

  const draftPayload = (expectedRevision) => ({
    expected_revision: expectedRevision,
    pozycje: tables.map((table) => ({
      stolik_id: table.id,
      ...positionsRef.current[table.id],
    })),
    krawedzie: normalizeEdges(edgesRef.current),
    kombinacje: normalizeCombinations(combinationsRef.current),
  })

  const persistDraft = async ({ quiet = false } = {}) => {
    if (mode !== 'draft' || !plan?.wersja || busy) return plan
    if (invalidTableProperties) {
      setPlanError({
        message: `Uzupełnij nazwę stołu #${invalidTableProperties.id} przed zapisaniem szkicu.`,
        action: null,
      })
      return null
    }
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
      setEdges([])
      edgesRef.current = []
      setCombinations([])
      combinationsRef.current = []
      const emptyHistory = { past: [], future: [] }
      setHistory(emptyHistory)
      historyRef.current = emptyHistory
      setFeatureDrafts({})
      baselineRef.current = editorSignature({}, [], [])
      setEditorTool('layout')
      setConnectionStartId(null)
      setConnectionTargetId('')
      setConnectionFeedback(null)
      setCheckerResult(null)
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
    <Card className="overflow-hidden" onKeyDown={handleEditorShortcut}>
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
                      <Button variant="ghost" size="sm" onClick={() => persistDraft()} loading={busy === 'save'} loadingLabel="Zapisuję…" disabled={Boolean(busy) || !dirty || Boolean(invalidTableProperties)}>Zapisz szkic</Button>
                      <Button variant="primary" size="sm" onClick={publishDraft} loading={busy === 'publish'} loadingLabel="Publikuję…" disabled={Boolean(busy) || Boolean(invalidTableProperties)}>Opublikuj</Button>
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
                      {planError.action ? (
                        <Button variant="ghost" size="sm" onClick={retryPlanError}>Spróbuj ponownie</Button>
                      ) : null}
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

              {mode === 'draft' && tables.length ? (
                <div className="mt-5 flex flex-col gap-3 border-y border-line py-3 sm:flex-row sm:items-center sm:justify-between" role="toolbar" aria-label="Narzędzia edycji planu">
                  <PillSwitch
                    options={[
                      { value: 'layout', label: 'Ustaw stoły' },
                      { value: 'connect', label: 'Połącz stoły' },
                    ]}
                    value={editorTool}
                    onChange={(nextTool) => {
                      setEditorTool(nextTool)
                      setConnectionStartId(null)
                      setConnectionTargetId('')
                      setConnectionFeedback(null)
                      setAnnouncement(nextTool === 'connect'
                        ? 'Tryb łączenia. Wybierz pierwszy stół, a potem stół stojący obok.'
                        : 'Tryb ustawiania stołów.')
                    }}
                    label="Tryb edycji planu"
                    disabled={Boolean(busy)}
                    className="w-full sm:w-[21rem]"
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="subtle"
                      size="sm"
                      onClick={undoEditor}
                      disabled={Boolean(busy) || history.past.length === 0}
                      aria-keyshortcuts="Control+Z Meta+Z"
                      className="flex-1 sm:flex-none"
                    >
                      Cofnij
                    </Button>
                    <Button
                      variant="subtle"
                      size="sm"
                      onClick={redoEditor}
                      disabled={Boolean(busy) || history.future.length === 0}
                      aria-keyshortcuts="Control+Shift+Z Meta+Shift+Z Control+Y"
                      className="flex-1 sm:flex-none"
                    >
                      Ponów
                    </Button>
                  </div>
                </div>
              ) : null}

              {connectionFeedback && mode === 'draft' && editorTool === 'connect' ? (
                <p
                  className={`mt-3 text-sm ${connectionFeedback.type === 'error' ? 'text-danger' : 'text-success'}`}
                  role={connectionFeedback.type === 'error' ? 'alert' : 'status'}
                >
                  {connectionFeedback.message}
                </p>
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
                  <>
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
                        <svg
                          aria-hidden="true"
                          focusable="false"
                          className="pointer-events-none absolute inset-0 z-0 h-full w-full"
                          viewBox="0 0 100 100"
                          preserveAspectRatio="none"
                        >
                          {edges.map((edge) => {
                            const first = positions[edge.stolik_a_id]
                            const second = positions[edge.stolik_b_id]
                            if (!first || !second) return null
                            const highlighted = connectionStartId === edge.stolik_a_id || connectionStartId === edge.stolik_b_id
                            return (
                              <line
                                key={edgeKey(edge.stolik_a_id, edge.stolik_b_id)}
                                x1={first.plan_x}
                                y1={first.plan_y}
                                x2={second.plan_x}
                                y2={second.plan_y}
                                vectorEffect="non-scaling-stroke"
                                stroke={highlighted ? '#9DC4B1' : 'rgba(244,244,245,0.34)'}
                                strokeWidth={highlighted ? 3 : 2}
                                strokeDasharray={highlighted ? undefined : '5 4'}
                              />
                            )
                          })}
                        </svg>
                        {tables.map((table) => {
                          const value = positions[table.id] || geometry(table)
                          const selected = table.id === selectedTableId
                          const connectionAnchor = table.id === connectionStartId
                          const neighbors = neighborIds(table.id, edges)
                            .map((id) => nameForTable(id))
                            .join(', ')
                          return (
                            <button
                              key={table.id}
                              type="button"
                              onPointerDown={(event) => onPointerDown(event, table.id)}
                              onKeyDown={(event) => onTableKeyDown(event, table.id)}
                              onClick={() => handleTableClick(table.id)}
                              disabled={Boolean(busy)}
                              aria-pressed={editorTool === 'connect' && mode === 'draft' ? connectionAnchor : selected}
                              aria-label={`${value.nazwa}, ${value.pojemnosc} ${placesLabel(value.pojemnosc)}, ${value.aktywny_w_planie ? 'aktywny w planie' : 'nieaktywny w planie'}, pozycja X ${Math.round(value.plan_x)}%, Y ${Math.round(value.plan_y)}%, ${neighbors ? `sąsiaduje z: ${neighbors}` : 'bez zaznaczonego sąsiedztwa'}`}
                              className={`absolute z-10 grid min-h-11 min-w-11 place-items-center rounded-xl border text-center transition-[border-color,background-color,box-shadow] duration-150 ${value.aktywny_w_planie ? 'border-white/[0.16] bg-surface-2 text-ink' : 'border-line bg-bg/80 text-muted'} ${selected || connectionAnchor ? 'ring-2 ring-mint ring-offset-2 ring-offset-bg' : 'hover:border-white/[0.24]'} ${busy ? 'cursor-wait' : mode === 'draft' && editorTool === 'layout' ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'}`}
                              style={{
                                left: `${value.plan_x}%`,
                                top: `${value.plan_y}%`,
                                width: `${value.szerokosc}%`,
                                height: `${value.wysokosc}%`,
                                transform: `translate(-50%, -50%) rotate(${value.obrot}deg)`,
                                touchAction: mode === 'draft' && editorTool === 'layout' && !busy ? 'none' : 'manipulation',
                              }}
                            >
                              <span style={{ transform: `rotate(${-value.obrot}deg)` }}>
                                <span className="block max-w-[8rem] truncate px-1 text-xs font-semibold">{value.nazwa}</span>
                                <span className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted"><Icon name="users" className="h-3 w-3" />{value.pojemnosc}</span>
                              </span>
                            </button>
                          )
                        })}
                        </div>
                      </div>
                      <p className="mt-3 text-xs leading-relaxed text-muted">
                        {mode === 'draft' && editorTool === 'connect'
                          ? connectionStartId
                            ? `${nameForTable(connectionStartId)} wybrany. Wybierz stół stojący obok; Escape anuluje wybór.`
                            : 'Wybierz pierwszy stół, a potem stół stojący obok. Na telefonie możesz użyć także listy tekstowej.'
                          : mode === 'draft'
                            ? 'Przeciągnij stół albo zaznacz go i użyj strzałek. Shift + strzałka przesuwa o 5%. Na małym ekranie przesuń cały plan w bok.'
                            : 'Wybierz stół, aby zobaczyć jego pozycję, rozmiar i sąsiedztwo. Na małym ekranie przesuń cały plan w bok.'}
                      </p>
                    </div>

                    <aside className="mt-5 border-t border-line pt-5 xl:mt-0 xl:border-l xl:border-t-0 xl:pl-6 xl:pt-0" aria-label="Szczegóły stołu">
                      {selectedTable ? (
                        <div>
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h4 className="truncate text-base font-semibold text-ink" title={selectedProperties.nazwa}>{selectedProperties.nazwa}</h4>
                              <p className="mt-1 text-xs text-muted">{selectedProperties.pojemnosc} {placesLabel(selectedProperties.pojemnosc)} · stabilny stół #{selectedTable.id}</p>
                            </div>
                            <span className={`rounded-full px-2 py-1 text-[0.68rem] font-semibold ${positions[selectedTable.id]?.aktywny_w_planie ? 'bg-success/10 text-success' : 'bg-white/[0.05] text-muted'}`}>
                              {positions[selectedTable.id]?.aktywny_w_planie ? 'Aktywny' : 'Nieaktywny'}
                            </span>
                          </div>

                          {mode !== 'draft' || editorTool === 'layout' ? <>
                          <div className="mt-5 grid grid-cols-2 gap-3">
                            <label className="field-label col-span-2">
                              Nazwa na planie
                              <input
                                data-editor-history
                                value={selectedProperties.nazwa}
                                onChange={(event) => setTableGeometry(selectedTable.id, { nazwa: event.target.value })}
                                maxLength={32}
                                required
                                disabled={mode !== 'draft' || Boolean(busy)}
                                className="field mt-1.5 min-h-11 normal-case tracking-normal"
                              />
                              {!selectedProperties.nazwa.trim() ? <span className="mt-1 block text-xs font-normal normal-case tracking-normal text-danger">Nazwa jest wymagana.</span> : null}
                            </label>
                            <label className="field-label">
                              Miejsca przy stole
                              <input
                                data-editor-history
                                type="number"
                                min="1"
                                value={selectedProperties.pojemnosc}
                                onChange={(event) => setTableGeometry(selectedTable.id, { pojemnosc: Number(event.target.value) })}
                                disabled={mode !== 'draft' || Boolean(busy)}
                                className="field mt-1.5 min-h-11 normal-case tracking-normal"
                              />
                            </label>
                            <label className="field-label">
                              Minimum osób
                              <input
                                data-editor-history
                                type="number"
                                min="1"
                                max={selectedProperties.pojemnosc}
                                value={selectedProperties.pojemnosc_min}
                                onChange={(event) => setTableGeometry(selectedTable.id, { pojemnosc_min: Number(event.target.value) })}
                                disabled={mode !== 'draft' || Boolean(busy)}
                                className="field mt-1.5 min-h-11 normal-case tracking-normal"
                              />
                            </label>
                            <label className="field-label col-span-2">
                              Kształt
                              <select
                                data-editor-history
                                value={selectedProperties.ksztalt || ''}
                                onChange={(event) => setTableGeometry(selectedTable.id, { ksztalt: event.target.value || null })}
                                disabled={mode !== 'draft' || Boolean(busy)}
                                className="field mt-1.5 min-h-11 normal-case tracking-normal"
                              >
                                <option value="">Bez oznaczenia</option>
                                {selectedProperties.ksztalt && !['kwadrat', 'okragly', 'prostokat'].includes(selectedProperties.ksztalt) ? (
                                  <option value={selectedProperties.ksztalt}>{selectedProperties.ksztalt}</option>
                                ) : null}
                                <option value="kwadrat">Kwadratowy</option>
                                <option value="okragly">Okrągły</option>
                                <option value="prostokat">Prostokątny</option>
                              </select>
                            </label>
                            <label className="field-label">
                              Priorytet
                              <input
                                data-editor-history
                                type="number"
                                value={selectedProperties.priorytet}
                                onChange={(event) => setTableGeometry(selectedTable.id, { priorytet: Number(event.target.value) })}
                                disabled={mode !== 'draft' || Boolean(busy)}
                                className="field mt-1.5 min-h-11 normal-case tracking-normal"
                              />
                            </label>
                            <label className="field-label">
                              Sekcja
                              <input
                                data-editor-history
                                value={selectedProperties.sekcja || ''}
                                onChange={(event) => setTableGeometry(selectedTable.id, { sekcja: event.target.value })}
                                maxLength={32}
                                disabled={mode !== 'draft' || Boolean(busy)}
                                className="field mt-1.5 min-h-11 normal-case tracking-normal"
                                placeholder="np. A"
                              />
                            </label>
                            <label className="field-label col-span-2">
                              Cechy
                              <input
                                data-editor-history
                                value={featureDrafts[selectedTable.id] ?? (selectedProperties.cechy || []).join(', ')}
                                onChange={(event) => {
                                  const raw = event.target.value
                                  setFeatureDrafts((current) => ({ ...current, [selectedTable.id]: raw }))
                                  setTableGeometry(selectedTable.id, {
                                    cechy: raw.split(',').map((item) => item.trim()).filter(Boolean),
                                  })
                                }}
                                disabled={mode !== 'draft' || Boolean(busy)}
                                className="field mt-1.5 min-h-11 normal-case tracking-normal"
                                placeholder="np. okno, loża, dostępny dla wózka"
                              />
                            </label>
                          </div>

                          <p className="mt-3 text-xs leading-relaxed text-muted">Niższa liczba zwiększa szansę wyboru przy podobnym dopasowaniu. Silnik nadal uwzględnia liczbę miejsc, łączenie stołów i pozostałe reguły.</p>

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
                                    data-editor-history
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
                          </> : null}

                          {mode === 'published' || editorTool === 'connect' ? (
                            <section className="mt-5 border-t border-line pt-5" aria-labelledby={`connections-${selectedTable.id}`}>
                              <h5 id={`connections-${selectedTable.id}`} className="text-sm font-semibold text-ink">Sąsiedztwo</h5>
                              {selectedNeighbors.length ? (
                                <ul className="mt-3 space-y-2" aria-label={`${selectedTable.nazwa} sąsiaduje z`}>
                                  {selectedNeighbors.map((neighbor) => (
                                    <li key={neighbor.id} className="flex min-h-11 items-center justify-between gap-2 border-b border-line pb-2 text-sm">
                                      <span className="truncate text-ink" title={neighbor.nazwa}>{neighbor.nazwa}</span>
                                      {mode === 'draft' ? (
                                        <Button
                                          variant="subtle"
                                          size="sm"
                                          onClick={() => toggleEdge(selectedTable.id, neighbor.id)}
                                          disabled={Boolean(busy)}
                                          aria-label={`Usuń połączenie ${selectedTable.nazwa} z ${neighbor.nazwa}`}
                                        >
                                          Usuń
                                        </Button>
                                      ) : null}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-2 text-sm text-muted">Ten stół nie ma zaznaczonych sąsiadów.</p>
                              )}

                              {mode === 'draft' ? (
                                <form className="mt-4 space-y-2" onSubmit={addTextConnection}>
                                  <label className="field-label" htmlFor={`connection-target-${selectedTable.id}`}>Dodaj sąsiedni stół</label>
                                  <select
                                    id={`connection-target-${selectedTable.id}`}
                                    className="field min-h-11 normal-case tracking-normal"
                                    value={connectionTargetId}
                                    onChange={(event) => setConnectionTargetId(event.target.value)}
                                    disabled={Boolean(busy)}
                                  >
                                    <option value="">Wybierz stół</option>
                                    {activeTables.filter((table) => (
                                      table.id !== selectedTable.id && !selectedNeighborIds.includes(table.id)
                                    )).map((table) => (
                                      <option key={table.id} value={table.id}>{table.nazwa}</option>
                                    ))}
                                  </select>
                                  <Button type="submit" variant="ghost" size="sm" className="w-full" disabled={Boolean(busy) || !connectionTargetId}>
                                    Połącz stoły
                                  </Button>
                                </form>
                              ) : null}
                            </section>
                          ) : null}
                        </div>
                      ) : (
                        <div className="py-8 text-center text-sm text-muted">Wybierz stół na planie.</div>
                      )}
                    </aside>
                  </div>

                  {mode === 'published' || editorTool === 'connect' ? (
                    <div className="mt-6 border-t border-line pt-6">
                      <div className={`grid gap-7 ${mode === 'draft' ? 'lg:grid-cols-2' : ''}`}>
                        {mode === 'draft' ? (
                          <section aria-labelledby="proposed-combinations-heading">
                            <h4 id="proposed-combinations-heading" className="text-base font-semibold text-ink">
                              {proposalFocusTable ? `Proponowane zestawy dla ${proposalFocusTable.nazwa}` : 'Proponowane zestawy'}
                            </h4>
                            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Propozycje powstają z połączeń wybranego stołu. Stoły mogą mieć różną liczbę miejsc, np. 4 + 2. Zestaw zadziała po zatwierdzeniu i publikacji planu.</p>
                            {proposedCombinations.length ? (
                              <ul className="mt-4 max-h-72 space-y-2 overflow-y-auto pr-1">
                                {proposedCombinations.map((proposal) => {
                                  const capacityBreakdown = combinationCapacityBreakdown(
                                    proposal,
                                    activeTables,
                                  )
                                  return (
                                    <li key={combinationKey(proposal)} className="flex min-h-14 items-center justify-between gap-3 border-b border-line py-2">
                                      <div className="min-w-0">
                                        <p className="truncate text-sm font-medium text-ink" title={proposal.nazwa}>{proposal.nazwa}</p>
                                        {capacityBreakdown ? (
                                          <p className="mt-0.5 text-xs font-medium text-ink/80">Miejsca: {capacityBreakdown.label}</p>
                                        ) : null}
                                        <p className="mt-0.5 text-xs text-muted">Dla {proposal.pojemnosc_min}–{proposal.pojemnosc_max} osób · {proposal.stoliki.length} {tablesLabel(proposal.stoliki.length)}</p>
                                      </div>
                                      <Button variant="ghost" size="sm" onClick={() => approveCombination(proposal)} disabled={Boolean(busy)}>
                                        Zatwierdź
                                      </Button>
                                    </li>
                                  )
                                })}
                              </ul>
                            ) : (
                              <p className="mt-4 text-sm text-muted">
                                {proposalFocusTable
                                  ? 'Ten stół nie tworzy jeszcze nowego zestawu. Dodaj połączenie albo wybierz inny stół.'
                                  : 'Wybierz aktywny stół na planie, aby zobaczyć jego propozycje.'}
                              </p>
                            )}
                          </section>
                        ) : null}

                        <section aria-labelledby="approved-combinations-heading">
                          <h4 id="approved-combinations-heading" className="text-base font-semibold text-ink">Zatwierdzone zestawy</h4>
                          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Silnik może użyć tylko aktywnych zestawów, po zapisaniu i opublikowaniu planu.</p>
                          {combinations.length ? (
                            <ul className="mt-4 space-y-4">
                              {combinations.map((combination) => {
                                const key = combinationKey(combination)
                                const capacityBreakdown = combinationCapacityBreakdown(
                                  combination,
                                  combination.stoliki.map((tableId) => ({
                                    id: tableId,
                                    ...positions[tableId],
                                  })),
                                )
                                const physicalCapacity = capacityBreakdown?.total || 0
                                const hasInactiveMember = combination.stoliki.some((tableId) => (
                                  positions[tableId]?.aktywny_w_planie === false
                                ))
                                return (
                                  <li key={key} className={`border-b border-line pb-4 ${combination.aktywna_w_planie ? '' : 'text-muted'}`}>
                                    <div className="flex min-h-11 items-center justify-between gap-3">
                                      <div className="min-w-0">
                                        <div className="flex flex-wrap items-center gap-2">
                                          <p className={`truncate text-sm font-semibold ${combination.aktywna_w_planie ? 'text-ink' : 'text-muted'}`} title={combination.nazwa}>{combination.nazwa}</p>
                                          <span className={`rounded-full px-2 py-1 text-[0.68rem] font-semibold ${combination.aktywna_w_planie ? 'bg-success/10 text-success' : 'bg-white/[0.05] text-muted'}`}>
                                            {combination.aktywna_w_planie ? 'Aktywny' : 'Wyłączony'}
                                          </span>
                                        </div>
                                        {mode === 'published' ? (
                                          <p className="mt-1 text-xs text-muted">{combination.pojemnosc_min}–{combination.pojemnosc_max} osób · {combination.kanal === 'oba' ? 'online i przez obsługę' : combination.kanal === 'online' ? 'online' : 'przez obsługę'}</p>
                                        ) : null}
                                        {capacityBreakdown ? (
                                          <p className="mt-0.5 text-xs font-medium text-ink/80">Miejsca: {capacityBreakdown.label}</p>
                                        ) : null}
                                      </div>
                                      {mode === 'draft' ? (
                                        <Button variant="subtle" size="sm" onClick={() => removeCombination(key)} disabled={Boolean(busy)} aria-label={`Usuń zestaw ${combination.nazwa}`}>
                                          Usuń
                                        </Button>
                                      ) : null}
                                    </div>
                                    {mode === 'draft' ? (
                                      <>
                                      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                                        <label className="field-label">
                                          Od osób
                                          <input
                                            data-editor-history
                                            type="number"
                                            min="1"
                                            max={combination.pojemnosc_max}
                                            value={combination.pojemnosc_min}
                                            onChange={(event) => updateCombination(key, { pojemnosc_min: Number(event.target.value) })}
                                            className="field mt-1.5 min-h-11 normal-case tracking-normal"
                                            disabled={Boolean(busy)}
                                          />
                                        </label>
                                        <label className="field-label">
                                          Do osób
                                          <input
                                            data-editor-history
                                            type="number"
                                            min={combination.pojemnosc_min}
                                            max={physicalCapacity}
                                            value={combination.pojemnosc_max}
                                            onChange={(event) => updateCombination(key, { pojemnosc_max: Number(event.target.value) })}
                                            className="field mt-1.5 min-h-11 normal-case tracking-normal"
                                            disabled={Boolean(busy)}
                                          />
                                        </label>
                                        <label className="field-label">
                                          Kanał
                                          <select
                                            value={combination.kanal}
                                            onChange={(event) => updateCombination(key, { kanal: event.target.value })}
                                            className="field mt-1.5 min-h-11 normal-case tracking-normal"
                                            disabled={Boolean(busy)}
                                          >
                                            <option value="oba">Online i przez obsługę</option>
                                            <option value="wewnetrzna">Tylko przez obsługę</option>
                                            <option value="online">Tylko online</option>
                                          </select>
                                        </label>
                                        <label className="field-label">
                                          Priorytet obsadzania
                                          <input
                                            data-editor-history
                                            type="number"
                                            step="1"
                                            value={combination.priorytet}
                                            onChange={(event) => updateCombination(key, { priorytet: Number(event.target.value) })}
                                            className="field mt-1.5 min-h-11 normal-case tracking-normal"
                                            disabled={Boolean(busy)}
                                          />
                                        </label>
                                        <div>
                                          <span className="field-label">Status</span>
                                          <label className="mt-1.5 flex min-h-11 items-center gap-3 rounded-xl border border-line bg-surface-2 px-3 text-sm font-medium normal-case tracking-normal text-ink">
                                            <input
                                              type="checkbox"
                                              checked={Boolean(combination.aktywna_w_planie)}
                                              onChange={(event) => updateCombination(key, { aktywna_w_planie: event.target.checked })}
                                              disabled={Boolean(busy) || hasInactiveMember}
                                              aria-label={`Aktywny zestaw ${combination.nazwa}`}
                                            />
                                            {hasInactiveMember
                                              ? 'Najpierw włącz stoły'
                                              : combination.aktywna_w_planie ? 'Używany' : 'Wyłączony'}
                                          </label>
                                        </div>
                                      </div>
                                      <p className="mt-2 text-xs leading-relaxed text-muted">Niższa liczba zwiększa szansę wyboru przy podobnym dopasowaniu. Silnik nadal uwzględnia liczbę miejsc, liczbę łączonych stołów i pozostałe reguły.</p>
                                      </>
                                    ) : null}
                                  </li>
                                )
                              })}
                            </ul>
                          ) : (
                            <p className="mt-4 text-sm text-muted">Nie zatwierdzono jeszcze żadnego zestawu.</p>
                          )}
                        </section>
                      </div>

                      <section className="mt-7 border-t border-line pt-6" aria-labelledby="structure-check-heading">
                        <h4 id="structure-check-heading" className="text-base font-semibold text-ink">Sprawdź układ</h4>
                        <form className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={checkStructure}>
                          <label className="field-label sm:w-40">
                            Liczba osób
                            <input
                              type="number"
                              min="1"
                              value={checkerPeople}
                              onChange={(event) => {
                                setCheckerPeople(event.target.value)
                                setCheckerResult(null)
                              }}
                              className="field mt-1.5 min-h-11 normal-case tracking-normal"
                            />
                          </label>
                          <label className="field-label sm:w-52">
                            Kanał rezerwacji
                            <select
                              value={checkerChannel}
                              onChange={(event) => {
                                setCheckerChannel(event.target.value)
                                setCheckerResult(null)
                              }}
                              className="field mt-1.5 min-h-11 normal-case tracking-normal"
                            >
                              <option value="wewnetrzna">Przez obsługę / recepcję</option>
                              <option value="online">Online</option>
                            </select>
                          </label>
                          <Button type="submit" variant="ghost" size="sm">Sprawdź</Button>
                        </form>
                        <p className="mt-3 text-xs leading-relaxed text-muted">Sprawdzamy aktywne stoły i zestawy dostępne w wybranym kanale. Wynik stosuje ten sam podstawowy ranking co silnik, ale nie uwzględnia dostępności w konkretnym terminie ani bieżącego obciążenia sekcji.</p>
                        {checkerResult ? (
                          <p className={`mt-3 text-sm font-medium ${checkerResult.match ? 'text-success' : 'text-lemon'}`} role="status">
                            {checkerResult.match
                              ? `Ten układ obsłuży ${checkerResult.people} osób: ${checkerResult.match.name}.`
                              : `Brak zatwierdzonego zestawu lub pojedynczego stołu dla ${checkerResult.people} osób.`}
                          </p>
                        ) : null}
                      </section>
                    </div>
                  ) : null}
                  </>
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
