import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { api } from '../../lib/api'
import {
  buildReservationHash,
  navigateReservationRoute,
  normalizeReservationRoute,
  readReservationRoute,
  subscribeReservationRoute,
} from '../../lib/reservationRoute'
import {
  readReservationSession,
  reservationHistoryBelongsTo,
  reservationHistoryState,
  writeReservationSession,
} from '../../lib/reservationSession'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import { Icon } from '../../lib/icons'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { useToast } from '../ui/Toast'
import RezerwacjeStolik from './RezerwacjeStolik'
import WidokHosta from './WidokHosta'
import ReservationsCalendar from './ReservationsCalendar'
import ReservationsDatabase from './ReservationsDatabase'
import GuestProfileDialog from './GuestProfileDialog'
import PlanSali from './PlanSali'

const VIEW_META = {
  today: { label: 'Dzisiaj', icon: 'clock' },
  calendar: { label: 'Kalendarz', icon: 'calendar' },
  database: { label: 'Baza', icon: 'server' },
  host: { label: 'Host', icon: 'users' },
}

const scrollElement = (root) => {
  const main = root?.closest('main')
  const mainClasses = typeof main?.className === 'string' ? main.className : ''
  const mainOverflow = main && typeof window.getComputedStyle === 'function'
    ? window.getComputedStyle(main).overflowY
    : ''
  if (main && (/\boverflow-y-(?:auto|scroll)\b/.test(mainClasses) || ['auto', 'scroll'].includes(mainOverflow))) {
    return main
  }
  return document.scrollingElement || document.documentElement
}

export default function ReservationsWorkspace() {
  const { user, can, isAdmin } = useAuth()
  const { confirm } = useToast()
  const rootRef = useRef(null)
  const remembered = useRef(readReservationSession(user))
  const scrollPositions = useRef(remembered.current?.scroll || {})
  const previousView = useRef(null)
  const scrollContainerRef = useRef(null)
  const pendingScrollRestore = useRef(null)
  const selectionDates = useRef(new Map())
  const selectionControllerRef = useRef(null)
  const guestProfileDirtyRef = useRef(false)
  const guestBackGuardRef = useRef({
    bypass: false,
    confirming: false,
    generation: 0,
    promptAfterRestore: false,
    restoring: false,
    restoringProfileId: null,
  })
  const lastSelectionId = useRef(null)
  const [selectionReady, setSelectionReady] = useState(null)
  const [selectionError, setSelectionError] = useState(null)
  const [selectionRetry, setSelectionRetry] = useState(0)
  const [privacyVersion, setPrivacyVersion] = useState(0)

  const has = useCallback((permission) => isAdmin || can(permission), [can, isAdmin])
  const canOperate = has('rezerwacje.operacje')
  const canHost = has('rezerwacje.host')
  const canViewContacts = has('rezerwacje.dane_kontaktowe')
  const canConfigureRooms = has('rezerwacje.sala')

  const operationalViews = useMemo(() => [
    ...(canOperate ? ['today', 'calendar'] : []),
    ...(canOperate && canViewContacts ? ['database'] : []),
    ...(canHost ? ['host'] : []),
  ], [canHost, canOperate, canViewContacts])
  const availableViews = useMemo(() => [
    ...operationalViews,
    ...(canConfigureRooms ? ['rooms'] : []),
  ], [canConfigureRooms, operationalViews])

  const [route, setRoute] = useState(() => {
    const fromUrl = readReservationRoute()
    const safeUrl = fromUrl && reservationHistoryBelongsTo(user, window.history.state) ? fromUrl : null
    return normalizeReservationRoute(
      safeUrl || remembered.current?.route || { view: availableViews[0] || 'today' },
    )
  })
  const routeRef = useRef(route)
  const safeView = availableViews.includes(route.view) ? route.view : availableViews[0]
  const lastOperationalView = useRef(
    operationalViews.includes(safeView) ? safeView : (operationalViews[0] || 'today'),
  )
  const [visited, setVisited] = useState(() => new Set(safeView ? [safeView] : []))

  const commitRoute = useCallback((value, options = {}) => {
    const next = normalizeReservationRoute(value)
    routeRef.current = next
    setRoute(next)
    navigateReservationRoute(next, {
      ...options,
      state: {
        ...(options.state || {}),
        ...reservationHistoryState(user),
      },
    })
  }, [user])

  const patchRoute = useCallback((patch, options = {}) => {
    const current = routeRef.current
    const nextPatch = typeof patch === 'function' ? patch(current) : patch
    commitRoute({ ...current, ...nextPatch }, options)
  }, [commitRoute])

  const handleRoomChange = useCallback((roomId) => {
    patchRoute({ roomId }, { replace: true })
  }, [patchRoute])

  const handleOpenRooms = useCallback(() => {
    patchRoute({
      view: 'rooms',
      reservationId: null,
      profileReservationId: null,
    })
  }, [patchRoute])

  const handleGuestProfileDirtyChange = useCallback((dirty) => {
    guestProfileDirtyRef.current = Boolean(dirty)
  }, [])

  const restorePendingScroll = useCallback(() => {
    const container = scrollContainerRef.current
    const target = pendingScrollRestore.current
    if (!container || target == null) return
    const maxScroll = Math.max(0, container.scrollHeight - container.clientHeight)
    container.scrollTop = Math.min(target, maxScroll)
    if (maxScroll >= target) pendingScrollRestore.current = null
  }, [])

  useEffect(() => {
    let active = true
    const guard = guestBackGuardRef.current

    const applyRoute = (next) => {
      if (!next) {
        const fallback = normalizeReservationRoute({
          ...(remembered.current?.route || {}),
          view: availableViews[0] || 'today',
          reservationId: null,
          profileReservationId: null,
        })
        routeRef.current = fallback
        setRoute(fallback)
        return
      }
      if (!reservationHistoryBelongsTo(user, window.history.state)) {
        commitRoute(remembered.current?.route || { view: availableViews[0] || 'today' }, { replace: true })
        return
      }
      routeRef.current = next
      setRoute(next)
    }

    const confirmRestoredBack = () => {
      if (!guard.promptAfterRestore || guard.confirming) return
      guard.promptAfterRestore = false
      guard.confirming = true
      const generation = guard.generation
      void confirm(
        'Odrzucić niezapisane zmiany w profilu gościa?',
        {
          title: 'Niezapisane zmiany',
          confirmText: 'Odrzuć zmiany',
          cancelText: 'Wróć do profilu',
        },
      ).then((discard) => {
        if (!active || guard.generation !== generation) return
        guard.confirming = false
        if (!discard) return
        guard.bypass = true
        window.history.back()
      })
    }

    const unsubscribe = subscribeReservationRoute((next, event) => {
      const eventType = event?.type

      // Pierwszy Back już przesunął wskaźnik historii. Wracamy istniejącym
      // wpisem forward (bez tworzenia duplikatu), a dopiero potem pytamy o szkic.
      if (guard.restoring) {
        if (eventType === 'hashchange') return
        if (eventType === 'popstate') {
          if (next?.profileReservationId !== guard.restoringProfileId) {
            window.history.forward()
            return
          }
          guard.restoring = false
          guard.restoringProfileId = null
          applyRoute(next)
          confirmRestoredBack()
          return
        }
      }

      if (guard.bypass && eventType === 'popstate') {
        guard.bypass = false
        applyRoute(next)
        return
      }

      const currentProfileId = routeRef.current.profileReservationId
      const closesDirtyProfile = Boolean(
        currentProfileId
        && next?.profileReservationId !== currentProfileId
        && guestProfileDirtyRef.current,
      )
      if (eventType === 'popstate' && closesDirtyProfile) {
        guard.restoring = true
        guard.restoringProfileId = currentProfileId
        guard.promptAfterRestore = !guard.confirming
        window.history.forward()
        return
      }

      applyRoute(next)
    })

    return () => {
      active = false
      guard.generation += 1
      guard.bypass = false
      guard.confirming = false
      guard.promptAfterRestore = false
      guard.restoring = false
      guard.restoringProfileId = null
      unsubscribe()
    }
  }, [availableViews, commitRoute, confirm, user])

  useEffect(() => {
    if (!availableViews.length) return
    const nextView = availableViews.includes(route.view) ? route.view : availableViews[0]
    const mustClearSelection = (!canOperate || !canViewContacts)
      && (route.reservationId || route.profileReservationId)
    const canonical = normalizeReservationRoute({
      ...route,
      view: nextView,
      reservationId: mustClearSelection ? null : route.reservationId,
      profileReservationId: mustClearSelection ? null : route.profileReservationId,
    })
    const currentHash = readReservationRoute()
    const needsUrl = !currentHash
      || buildReservationHash(canonical) !== window.location.hash
      || !reservationHistoryBelongsTo(user, window.history.state)
    if (
      canonical.view !== route.view
      || canonical.reservationId !== route.reservationId
      || canonical.profileReservationId !== route.profileReservationId
      || needsUrl
    ) {
      commitRoute(canonical, { replace: true })
    }
  }, [availableViews, canOperate, canViewContacts, commitRoute, route, user])

  useEffect(() => {
    const reservationId = route.reservationId
    if (lastSelectionId.current && lastSelectionId.current !== reservationId) {
      selectionDates.current.delete(lastSelectionId.current)
    }
    if (!reservationId || !canOperate || !canViewContacts) {
      if (reservationId) selectionDates.current.delete(reservationId)
      lastSelectionId.current = null
      setSelectionReady(null)
      return undefined
    }
    lastSelectionId.current = reservationId
    const knownDate = selectionDates.current.get(reservationId)
    if (knownDate) {
      if (route.view !== 'today' || route.date !== knownDate) {
        commitRoute({ ...route, view: 'today', date: knownDate }, { replace: true })
      }
      setSelectionReady(reservationId)
      setSelectionError(null)
      return undefined
    }

    let current = true
    const controller = new AbortController()
    selectionControllerRef.current?.abort()
    selectionControllerRef.current = controller
    setSelectionReady(null)
    setSelectionError(null)
    api(`/rezerwacje-stolik/${reservationId}`, 'GET', null, { signal: controller.signal })
      .then((reservation) => {
        if (!current || controller.signal.aborted) return
        selectionDates.current.set(reservationId, reservation.data)
        if (routeRef.current.view !== 'today' || routeRef.current.date !== reservation.data) {
          commitRoute({
            ...routeRef.current,
            view: 'today',
            date: reservation.data,
            reservationId,
          }, { replace: true })
        }
        setSelectionReady(reservationId)
      })
      .catch((error) => {
        if (!current || controller.signal.aborted || error?.name === 'AbortError') return
        setSelectionError(error.message || 'Nie udało się otworzyć wskazanej rezerwacji.')
        if ([403, 404].includes(error?.status)) {
          selectionDates.current.delete(reservationId)
          patchRoute({ reservationId: null, profileReservationId: null }, { replace: true })
        }
      })
    return () => {
      current = false
      controller.abort()
      if (selectionControllerRef.current === controller) selectionControllerRef.current = null
    }
  }, [canOperate, canViewContacts, commitRoute, patchRoute, route, selectionRetry])

  useEffect(() => {
    if (!safeView) return
    setVisited((current) => {
      if (current.has(safeView)) return current
      const next = new Set(current)
      next.add(safeView)
      return next
    })
  }, [safeView])

  useEffect(() => {
    if (operationalViews.includes(safeView)) lastOperationalView.current = safeView
  }, [operationalViews, safeView])

  useEffect(() => subscribeReservationPrivacyPurge(() => {
    guestProfileDirtyRef.current = false
    const guard = guestBackGuardRef.current
    guard.bypass = false
    guard.confirming = false
    guard.generation += 1
    guard.promptAfterRestore = false
    guard.restoring = false
    guard.restoringProfileId = null
    selectionControllerRef.current?.abort()
    selectionControllerRef.current = null
    selectionDates.current.clear()
    lastSelectionId.current = null
    setSelectionReady(null)
    setSelectionError(null)
    setSelectionRetry(0)
    setVisited(new Set(safeView ? [safeView] : []))
    setPrivacyVersion((value) => value + 1)
    const fromUrl = readReservationRoute()
    const cleanRoute = normalizeReservationRoute({
      ...(fromUrl || routeRef.current),
      view: availableViews.includes(fromUrl?.view)
        ? fromUrl.view
        : (availableViews[0] || 'today'),
      reservationId: null,
      profileReservationId: null,
    })
    routeRef.current = cleanRoute
    setRoute(cleanRoute)
  }), [availableViews, safeView])

  useLayoutEffect(() => {
    if (!safeView) return
    const container = scrollElement(rootRef.current)
    scrollContainerRef.current = container
    const previous = previousView.current
    if (container) {
      if (previous && previous !== safeView) {
        scrollPositions.current[previous] = Math.max(0, container.scrollTop || 0)
      }
      if (previous !== safeView) {
        pendingScrollRestore.current = scrollPositions.current[safeView] || 0
        restorePendingScroll()
      }
    }
    previousView.current = safeView
  }, [restorePendingScroll, safeView])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return undefined
    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(restorePendingScroll)
      observer.observe(root)
      return () => observer.disconnect()
    }
    if (typeof MutationObserver !== 'undefined') {
      const observer = new MutationObserver(restorePendingScroll)
      observer.observe(root, { childList: true, subtree: true })
      return () => observer.disconnect()
    }
    return undefined
  }, [restorePendingScroll])

  useEffect(() => {
    if (!safeView) return
    writeReservationSession(user, { route: { ...route, view: safeView }, scroll: scrollPositions.current })
  }, [route, safeView, user])

  useEffect(() => () => {
    const view = previousView.current
    const container = scrollContainerRef.current
    if (view && container) scrollPositions.current[view] = Math.max(0, container.scrollTop || 0)
    writeReservationSession(user, { route: routeRef.current, scroll: scrollPositions.current })
  }, [user])

  const switchView = (view) => {
    if (view === safeView) return
    if (operationalViews.includes(view)) lastOperationalView.current = view
    if (routeRef.current.reservationId) selectionDates.current.delete(routeRef.current.reservationId)
    setSelectionError(null)
    patchRoute({
      view,
      roomId: view === 'rooms' ? routeRef.current.roomId : null,
      reservationId: null,
      profileReservationId: null,
    })
  }

  const openReservation = (reservation) => {
    const withDetails = canViewContacts ? reservation.id : null
    if (withDetails) selectionDates.current.set(withDetails, reservation.data)
    commitRoute({
      ...routeRef.current,
      view: 'today',
      date: reservation.data,
      reservationId: withDetails,
      profileReservationId: null,
    }, { state: withDetails ? { lokaloReservationOverlay: true } : {} })
  }

  const closeReservation = () => {
    if (routeRef.current.reservationId) selectionDates.current.delete(routeRef.current.reservationId)
    setSelectionError(null)
    if (window.history.state?.lokaloReservationOverlay) {
      window.history.back()
      return
    }
    patchRoute({ reservationId: null, profileReservationId: null }, { replace: true })
  }

  const openGuestProfile = (reservationId) => {
    if (!canOperate || !canViewContacts || !reservationId) return
    guestProfileDirtyRef.current = false
    const returnTo = normalizeReservationRoute({
      ...routeRef.current,
      reservationId,
      profileReservationId: null,
    })
    commitRoute({
      ...returnTo,
      profileReservationId: reservationId,
    }, {
      state: {
        lokaloReservationGuestOverlay: true,
        lokaloReservationReturnTo: returnTo,
      },
    })
  }

  const closeGuestProfile = ({ dirtyConfirmed = false } = {}) => {
    if (
      window.history.state?.lokaloReservationGuestOverlay
      && reservationHistoryBelongsTo(user, window.history.state)
    ) {
      if (dirtyConfirmed) guestBackGuardRef.current.bypass = true
      window.history.back()
      return
    }
    patchRoute({ profileReservationId: null }, { replace: true })
  }

  if (!safeView) {
    return (
      <div className="rounded-2xl border border-line bg-white/[0.02] px-5 py-10 text-center">
        <h2 className="font-display text-lg font-semibold text-ink">Brak dostępu do rezerwacji</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted">Administrator może przydzielić operacje rezerwacji lub widok hosta w ustawieniach konta.</p>
      </div>
    )
  }

  return (
    <div ref={rootRef} className="space-y-5">
      <div className="flex flex-col gap-4 border-b border-line pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-muted">
            {safeView === 'rooms' ? 'Ustawienia rezerwacji' : 'Workspace operacyjny'}
          </p>
          <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">
            {safeView === 'rooms' ? 'Konfiguracja sal' : 'Rezerwacje'}
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
            {safeView === 'rooms'
              ? 'Przygotuj układ jako szkic i opublikuj go dopiero, gdy jest gotowy do pracy.'
              : 'Plan dnia, kalendarz, historia i obsługa gości w jednym miejscu.'}
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          {operationalViews.length ? (
          <nav className="grid w-full grid-cols-4 gap-1 rounded-xl border border-line bg-white/[0.025] p-1 sm:flex sm:w-auto" aria-label="Widoki rezerwacji">
          {operationalViews.map((view) => {
            const meta = VIEW_META[view]
            const active = safeView === view
            return (
              <button
                key={view}
                type="button"
                onClick={() => switchView(view)}
                aria-current={active ? 'page' : undefined}
                className={`inline-flex min-h-12 min-w-0 flex-col items-center justify-center gap-1 rounded-lg px-1 text-[0.68rem] font-semibold transition active:scale-[0.98] sm:min-h-11 sm:shrink-0 sm:flex-row sm:gap-2 sm:px-3.5 sm:text-sm ${active ? 'bg-mint text-bg' : 'text-muted hover:bg-white/[0.05] hover:text-ink'}`}
              >
                <Icon name={meta.icon} className="h-4 w-4" />
                {meta.label}
              </button>
            )
          })}
          </nav>
          ) : null}
          {canConfigureRooms && operationalViews.length ? (
            <Button
              variant="ghost"
              size="sm"
              aria-current={safeView === 'rooms' ? 'page' : undefined}
              onClick={() => switchView(
                safeView === 'rooms' ? lastOperationalView.current : 'rooms'
              )}
              className="w-full shrink-0 sm:w-auto"
            >
              <Icon name={safeView === 'rooms' ? 'chevronDown' : 'office'} className={`h-4 w-4 ${safeView === 'rooms' ? 'rotate-90' : ''}`} />
              {safeView === 'rooms' ? 'Wróć do rezerwacji' : 'Konfiguracja sal'}
            </Button>
          ) : null}
        </div>
      </div>

      {selectionError ? (
        <div role="alert">
          <Banner variant="danger">
            <div className="flex flex-wrap items-center gap-3">
              <span>{selectionError}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => route.reservationId
                  ? setSelectionRetry((value) => value + 1)
                  : setSelectionError(null)}
              >
                {route.reservationId ? 'Ponów' : 'Zamknij'}
              </Button>
            </div>
          </Banner>
        </div>
      ) : null}

      {availableViews.includes('today') && visited.has('today') ? (
        <section hidden={safeView !== 'today'} inert={safeView !== 'today' ? '' : undefined} aria-label="Rezerwacje dnia">
          <RezerwacjeStolik
            key={`today:${privacyVersion}`}
            date={route.date}
            onDateChange={(date) => patchRoute({ date, reservationId: null, profileReservationId: null })}
            reservationId={canViewContacts && selectionReady === route.reservationId ? route.reservationId : null}
            suspendReservationDialog={Boolean(route.profileReservationId)}
            onReservationOpen={(reservationId) => {
              selectionDates.current.set(reservationId, route.date)
              patchRoute(
                { reservationId, profileReservationId: null },
                { state: { lokaloReservationOverlay: true } },
              )
            }}
            onReservationClose={closeReservation}
            onGuestProfileOpen={openGuestProfile}
            onOpenRooms={handleOpenRooms}
          />
        </section>
      ) : null}

      {availableViews.includes('calendar') && visited.has('calendar') ? (
        <section hidden={safeView !== 'calendar'} inert={safeView !== 'calendar' ? '' : undefined} aria-label="Kalendarz rezerwacji">
          <ReservationsCalendar
            key={`calendar:${privacyVersion}`}
            date={route.date}
            mode={route.mode}
            status={route.status}
            active={safeView === 'calendar'}
            canOpenDetails={canViewContacts}
            onContextChange={(patch, options) => patchRoute(patch, options)}
            onOpenDay={(date) => patchRoute({ view: 'today', date, reservationId: null, profileReservationId: null })}
            onOpenReservation={openReservation}
          />
        </section>
      ) : null}

      {availableViews.includes('database') && visited.has('database') ? (
        <section hidden={safeView !== 'database'} inert={safeView !== 'database' ? '' : undefined} aria-label="Baza rezerwacji">
          <ReservationsDatabase
            key={`database:${privacyVersion}`}
            route={route}
            active={safeView === 'database'}
            onContextChange={(patch, options) => patchRoute(patch, options)}
            onOpenReservation={openReservation}
          />
        </section>
      ) : null}

      {availableViews.includes('host') && visited.has('host') ? (
        <section hidden={safeView !== 'host'} inert={safeView !== 'host' ? '' : undefined} aria-label="Widok hosta">
          <WidokHosta
            key={`host:${privacyVersion}`}
            date={route.date}
            onDateChange={(date) => patchRoute({ date, reservationId: null, profileReservationId: null })}
            active={safeView === 'host'}
          />
        </section>
      ) : null}

      {availableViews.includes('rooms') && visited.has('rooms') ? (
        <section hidden={safeView !== 'rooms'} inert={safeView !== 'rooms' ? '' : undefined} aria-label="Konfiguracja sal">
          <PlanSali
            key={`rooms:${privacyVersion}`}
            roomId={route.roomId}
            active={safeView === 'rooms'}
            onRoomChange={handleRoomChange}
          />
        </section>
      ) : null}

      {canOperate && canViewContacts && route.profileReservationId ? (
        <GuestProfileDialog
          reservationId={route.profileReservationId}
          onClose={closeGuestProfile}
          onDirtyChange={handleGuestProfileDirtyChange}
          closeLabel="Wróć do rezerwacji"
        />
      ) : null}
    </div>
  )
}
