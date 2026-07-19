import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '../../lib/icons'

const FALLBACK_ROOM_ID = '__pozostale__'

const tableReservationIds = (reservation) => [
  reservation?.stolik_id,
  ...(reservation?.stoliki_dodatkowe || []),
].filter(Boolean)

const stateMeta = {
  occupied: {
    label: 'Na sali',
    tableClass: 'border-mint/45 bg-mint/15 text-ink',
    dotClass: 'bg-mint',
  },
  arrived: {
    label: 'Goście czekają',
    tableClass: 'border-lemon/45 bg-lemon/10 text-ink',
    dotClass: 'bg-lemon',
  },
  upcoming: {
    label: 'Nadchodząca',
    tableClass: 'border-info/35 bg-info/10 text-ink',
    dotClass: 'bg-info',
  },
  hold: {
    label: 'Oferta waitlisty',
    tableClass: 'border-coral/35 bg-coral/10 text-ink',
    dotClass: 'bg-coral',
  },
  live: {
    label: 'Zajęty w POS',
    tableClass: 'border-danger/35 bg-danger/10 text-ink',
    dotClass: 'bg-danger',
  },
  inactive: {
    label: 'Nieaktywny',
    tableClass: 'border-line bg-bg/70 text-muted opacity-65',
    dotClass: 'bg-muted',
  },
  free: {
    label: 'Bez aktywnej wizyty',
    tableClass: 'border-white/[0.14] bg-surface-2 text-ink',
    dotClass: 'bg-muted',
  },
}

const fallbackState = (table) => {
  if (!table.aktywny || table.status === 'nieaktywny') return 'inactive'
  if (table.status === 'wstrzymany') return 'hold'
  if (table.status === 'zajety_live' || table.live?.zajete) return 'live'
  return 'free'
}

const placesLabel = (count) => count === 1 ? 'miejsce' : count >= 2 && count <= 4 ? 'miejsca' : 'miejsc'

const offerDeadlineLabel = (value) => {
  if (!value) return null
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) return null
  return new Intl.DateTimeFormat('pl-PL', {
    timeZone: 'Europe/Warsaw',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(parsed)
}

const directionalTarget = (current, candidates, key) => {
  const currentX = Number(current?.plan_x ?? 50)
  const currentY = Number(current?.plan_y ?? 50)
  return candidates
    .filter((table) => {
      const dx = Number(table.plan_x ?? 50) - currentX
      const dy = Number(table.plan_y ?? 50) - currentY
      if (key === 'ArrowLeft') return dx < 0
      if (key === 'ArrowRight') return dx > 0
      if (key === 'ArrowUp') return dy < 0
      return dy > 0
    })
    .map((table) => {
      const dx = Math.abs(Number(table.plan_x ?? 50) - currentX)
      const dy = Math.abs(Number(table.plan_y ?? 50) - currentY)
      const score = ['ArrowLeft', 'ArrowRight'].includes(key) ? dx + dy * 2 : dy + dx * 2
      return { table, score }
    })
    .sort((first, second) => first.score - second.score || first.table.id - second.table.id)[0]?.table || null
}

export default function HostFloorPlan({
  floor,
  queue,
  offline = false,
  canViewContacts = false,
  placement = null,
  placementCandidates = [],
  placementGuestLabel = 'gościa',
  onPlacementTarget,
  onPlacementCancel,
}) {
  const rooms = useMemo(() => {
    const configured = (floor?.sale || []).map((room) => ({
      id: String(room.id),
      sourceId: room.id,
      name: room.nazwa,
      active: room.aktywna !== false,
    }))
    const hasFallback = (floor?.stoliki || []).some((table) => table.sala_id == null)
    return hasFallback
      ? [...configured, { id: FALLBACK_ROOM_ID, sourceId: null, name: configured.length ? 'Pozostałe' : 'Sala', active: true }]
      : configured
  }, [floor])
  const [roomId, setRoomId] = useState(null)
  const [selectedTableId, setSelectedTableId] = useState(null)
  const tableRefs = useRef(new Map())

  useEffect(() => {
    if (!rooms.length) {
      setRoomId(null)
      return
    }
    if (rooms.some((room) => room.id === roomId)) return
    setRoomId((rooms.find((room) => room.active) || rooms[0]).id)
  }, [roomId, rooms])

  const operationalState = useMemo(() => {
    const states = new Map()
    for (const entry of queue?.waitlista || []) {
      if (entry.status !== 'zaoferowano') continue
      const tableIds = [entry.hold_stolik_id, ...(entry.hold_stoliki_dodatkowe || [])]
        .map(Number).filter((id) => Number.isFinite(id) && id > 0)
      for (const tableId of tableIds) states.set(tableId, { kind: 'hold', waitlist: entry })
    }
    for (const reservation of queue?.nadchodzace || []) {
      const kind = reservation.faza_hosta === 'przybyl' ? 'arrived' : 'upcoming'
      for (const tableId of tableReservationIds(reservation)) {
        if (!states.has(tableId)) states.set(tableId, { kind, reservation })
      }
    }
    for (const reservation of queue?.na_sali || []) {
      for (const tableId of tableReservationIds(reservation)) {
        states.set(tableId, { kind: 'occupied', reservation })
      }
    }
    return states
  }, [queue])

  const tables = useMemo(() => (floor?.stoliki || []).filter((table) => (
    roomId === FALLBACK_ROOM_ID ? table.sala_id == null : String(table.sala_id) === roomId
  )), [floor, roomId])

  useEffect(() => {
    if (tables.some((table) => table.id === selectedTableId)) return
    setSelectedTableId(tables[0]?.id ?? null)
  }, [selectedTableId, tables])

  const selectedTable = tables.find((table) => table.id === selectedTableId) || null
  const selectedOperational = selectedTable ? operationalState.get(selectedTable.id) : null
  const selectedKind = selectedOperational?.kind || (selectedTable ? fallbackState(selectedTable) : 'free')
  const selectedMeta = stateMeta[selectedKind]
  const placementTableIds = useMemo(() => new Set(
    placementCandidates.flatMap((candidate) => candidate.tableIds || []),
  ), [placementCandidates])
  const selectedPlacementIds = useMemo(() => new Set(
    placementCandidates.find((candidate) => candidate.key === placement?.selectedKey)?.tableIds || [],
  ), [placement?.selectedKey, placementCandidates])

  useEffect(() => {
    if (!placement || !placementTableIds.size) return
    const visibleTarget = tables.find((table) => placementTableIds.has(table.id))
    if (visibleTarget) return
    const firstTarget = (floor?.stoliki || []).find((table) => placementTableIds.has(table.id))
    if (!firstTarget) return
    const targetRoomId = firstTarget.sala_id == null ? FALLBACK_ROOM_ID : String(firstTarget.sala_id)
    if (rooms.some((room) => room.id === targetRoomId)) setRoomId(targetRoomId)
  }, [floor, placement, placementTableIds, roomId, rooms, tables])

  useEffect(() => {
    if (!placement || !placementTableIds.size) return
    const preferred = tables.find((table) => table.id === placement.targetTableId && placementTableIds.has(table.id))
      || tables.find((table) => placementTableIds.has(table.id))
    if (!preferred) return
    setSelectedTableId(preferred.id)
    const timer = window.setTimeout(() => tableRefs.current.get(preferred.id)?.focus(), 0)
    return () => window.clearTimeout(timer)
  }, [placement?.focusToken, roomId])

  const handleTableKeyDown = (event, table) => {
    if (!placement) return
    if (event.key === 'Escape') {
      event.preventDefault()
      onPlacementCancel?.()
      return
    }
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
    const candidates = tables.filter((candidate) => placementTableIds.has(candidate.id) && candidate.id !== table.id)
    const next = directionalTarget(table, candidates, event.key)
    if (!next) return
    event.preventDefault()
    setSelectedTableId(next.id)
    tableRefs.current.get(next.id)?.focus()
  }

  if (!floor || rooms.length === 0) {
    return (
      <section aria-labelledby="host-floor-title" className="min-w-0">
        <PanelHeading id="host-floor-title" title="Plan sali" detail="Brak opublikowanego planu" />
        <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-line px-6 text-center">
          <div className="max-w-sm">
            <Icon name="office" className="mx-auto h-7 w-7 text-muted" />
            <p className="mt-3 text-sm font-semibold text-ink">Najpierw opublikuj plan sali</p>
            <p className="mt-1 text-xs leading-relaxed text-muted">Host zobaczy tutaj wyłącznie układ zatwierdzony do pracy.</p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section aria-labelledby="host-floor-title" className="min-w-0">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <PanelHeading
          id="host-floor-title"
          title="Plan sali"
          detail={`${tables.length} ${tables.length === 1 ? 'stolik' : tables.length >= 2 && tables.length <= 4 ? 'stoliki' : 'stolików'}`}
        />
        {rooms.length > 1 ? (
          <div className="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-line bg-white/[0.025] p-1" aria-label="Wybierz salę">
            {rooms.map((room) => (
              <button
                key={room.id}
                type="button"
                onClick={() => setRoomId(room.id)}
                aria-pressed={room.id === roomId}
                className={`min-h-11 shrink-0 rounded-lg px-3 text-xs font-semibold transition ${
                  room.id === roomId ? 'bg-surface-2 text-ink shadow-cta' : 'text-muted hover:bg-white/[0.05] hover:text-ink'
                }`}
              >
                {room.name}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {placement ? (
        <p id="host-floor-placement-help" className="sr-only">
          Wybierz stolik dla {placementGuestLabel}. Użyj Tab lub strzałek, Enter aby wybrać, Escape aby anulować.
        </p>
      ) : null}

      {tables.length ? (
        <>
          <div className="mt-4 overflow-x-auto pb-2">
            <div
              className="relative aspect-[4/3] w-full min-w-[34rem] overflow-hidden rounded-2xl border border-white/[0.10] bg-surface"
              aria-label={`Plan operacyjny: ${rooms.find((room) => room.id === roomId)?.name || 'sala'}`}
              aria-describedby={placement ? 'host-floor-placement-help' : undefined}
              role="group"
            >
              {tables.map((table) => {
                const operational = operationalState.get(table.id)
                const kind = operational?.kind || fallbackState(table)
                const meta = stateMeta[kind]
                const selected = table.id === selectedTableId
                const width = Math.max(9, Number(table.szerokosc) || 12)
                const height = Math.max(9, Number(table.wysokosc) || 12)
                const reservation = operational?.reservation
                const waitlist = operational?.waitlist
                const guest = canViewContacts ? reservation?.nazwisko || waitlist?.nazwisko || 'Gość' : 'Gość'
                const timer = kind === 'occupied' && reservation?.minuty_od_posadzenia != null
                  ? `${reservation.minuty_od_posadzenia} min`
                  : null
                const offerDeadline = offerDeadlineLabel(waitlist?.hold_do)
                const targetable = Boolean(placement && placementTableIds.has(table.id) && !offline)
                const placementSelected = targetable && (
                  table.id === placement?.targetTableId || selectedPlacementIds.has(table.id)
                )
                const placementMuted = Boolean(placement && !targetable)
                const baseLabel = `${table.nazwa}, ${table.pojemnosc} ${placesLabel(table.pojemnosc)}, ${meta.label}${reservation || waitlist ? `, ${guest}` : ''}${offerDeadline ? `, oferta do ${offerDeadline}` : ''}${timer ? `, ${timer}` : ''}`
                return (
                  <button
                    key={table.id}
                    type="button"
                    ref={(node) => {
                      if (node) tableRefs.current.set(table.id, node)
                      else tableRefs.current.delete(table.id)
                    }}
                    data-host-drop-table={targetable ? table.id : undefined}
                    onClick={(event) => {
                      setSelectedTableId(table.id)
                      if (targetable) onPlacementTarget?.(table.id, {
                        input: event.detail === 0 ? 'keyboard' : 'activation',
                      })
                    }}
                    onKeyDown={(event) => handleTableKeyDown(event, table)}
                    tabIndex={placementMuted ? -1 : 0}
                    aria-pressed={placement ? placementSelected : selected}
                    aria-disabled={placementMuted || undefined}
                    aria-label={`${baseLabel}${placement ? targetable ? `, wybierz dla ${placementGuestLabel}` : ', niedostępny jako cel' : ''}`}
                    className={`absolute z-10 grid min-h-11 min-w-11 place-items-center rounded-xl border text-center shadow-soft transition-[border-color,background-color,box-shadow,opacity] duration-150 ${meta.tableClass} ${placementSelected ? 'ring-2 ring-mint ring-offset-2 ring-offset-bg' : targetable ? 'border-mint/55 hover:border-mint hover:bg-mint/15' : placementMuted ? 'opacity-40' : selected ? 'ring-2 ring-mint ring-offset-2 ring-offset-bg' : 'hover:border-white/[0.28]'}`}
                    style={{
                      left: `${table.plan_x ?? 50}%`,
                      top: `${table.plan_y ?? 50}%`,
                      width: `${width}%`,
                      height: `${height}%`,
                      transform: `translate(-50%, -50%) rotate(${Number(table.obrot) || 0}deg)`,
                    }}
                  >
                    <span style={{ transform: `rotate(${-(Number(table.obrot) || 0)}deg)` }} className="max-w-full px-1">
                      <span className="block truncate text-xs font-semibold">{table.nazwa}</span>
                      <span className="mt-0.5 block truncate text-[0.65rem] font-medium opacity-80">
                        {timer || meta.label}
                      </span>
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {selectedTable ? (
            <div className="mt-2 flex flex-col gap-2 border-t border-line pt-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">{selectedTable.nazwa}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {selectedTable.pojemnosc} {placesLabel(selectedTable.pojemnosc)}
                  {selectedOperational?.reservation?.liczba_osob ? ` · ${selectedOperational.reservation.liczba_osob} os.` : ''}
                  {selectedOperational?.waitlist?.liczba_osob ? ` · ${selectedOperational.waitlist.liczba_osob} os.` : ''}
                  {selectedOperational?.reservation?.godz_od ? ` · ${selectedOperational.reservation.godz_od}` : ''}
                  {selectedOperational?.waitlist?.hold_godz_od ? ` · ${selectedOperational.waitlist.hold_godz_od}` : ''}
                </p>
              </div>
              <span className="inline-flex min-h-8 shrink-0 items-center gap-2 self-start rounded-full border border-line bg-white/[0.035] px-3 text-xs font-semibold text-ink sm:self-auto">
                <span className={`h-2 w-2 rounded-full ${selectedMeta.dotClass}`} aria-hidden />
                {selectedMeta.label}{offline ? ' · tylko podgląd' : ''}
              </span>
            </div>
          ) : null}
        </>
      ) : (
        <div className="mt-4 grid min-h-64 place-items-center rounded-2xl border border-dashed border-line px-6 text-center text-sm text-muted">
          Ta sala nie ma stolików w opublikowanym planie.
        </div>
      )}
    </section>
  )
}

function PanelHeading({ id, title, detail }) {
  return (
    <div>
      <h3 id={id} className="text-base font-semibold text-ink">{title}</h3>
      <p className="mt-0.5 text-xs text-muted">{detail}</p>
    </div>
  )
}
