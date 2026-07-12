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
  reservationActorKey,
  writeReservationSession,
} from '../../lib/reservationSession'
import { Icon } from '../../lib/icons'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import RezerwacjeStolik from './RezerwacjeStolik'
import WidokHosta from './WidokHosta'
import ReservationsCalendar from './ReservationsCalendar'
import ReservationsDatabase from './ReservationsDatabase'

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
  const actorKey = reservationActorKey(user)
  const rootRef = useRef(null)
  const remembered = useRef(readReservationSession(user))
  const scrollPositions = useRef(remembered.current?.scroll || {})
  const previousView = useRef(null)
  const scrollContainerRef = useRef(null)
  const pendingScrollRestore = useRef(null)
  const selectionDates = useRef(new Map())
  const lastSelectionId = useRef(null)
  const [selectionReady, setSelectionReady] = useState(null)
  const [selectionError, setSelectionError] = useState(null)
  const [selectionRetry, setSelectionRetry] = useState(0)

  const has = useCallback((permission) => isAdmin || can(permission), [can, isAdmin])
  const canOperate = has('rezerwacje.operacje')
  const canHost = has('rezerwacje.host')
  const canViewContacts = has('rezerwacje.dane_kontaktowe')

  const availableViews = useMemo(() => [
    ...(canOperate ? ['today', 'calendar'] : []),
    ...(canOperate && canViewContacts ? ['database'] : []),
    ...(canHost ? ['host'] : []),
  ], [canHost, canOperate, canViewContacts])

  const [route, setRoute] = useState(() => {
    const fromUrl = readReservationRoute()
    const historyActor = window.history.state?.lokaloReservationActor
    const safeUrl = fromUrl && (!historyActor || historyActor === actorKey) ? fromUrl : null
    return normalizeReservationRoute(
      safeUrl || remembered.current?.route || { view: availableViews[0] || 'today' },
    )
  })
  const routeRef = useRef(route)
  const safeView = availableViews.includes(route.view) ? route.view : availableViews[0]
  const [visited, setVisited] = useState(() => new Set(safeView ? [safeView] : []))

  const commitRoute = useCallback((value, options = {}) => {
    const next = normalizeReservationRoute(value)
    routeRef.current = next
    setRoute(next)
    navigateReservationRoute(next, {
      ...options,
      state: {
        ...(options.state || {}),
        ...(actorKey ? { lokaloReservationActor: actorKey } : {}),
      },
    })
  }, [actorKey])

  const patchRoute = useCallback((patch, options = {}) => {
    const current = routeRef.current
    const nextPatch = typeof patch === 'function' ? patch(current) : patch
    commitRoute({ ...current, ...nextPatch }, options)
  }, [commitRoute])

  const restorePendingScroll = useCallback(() => {
    const container = scrollContainerRef.current
    const target = pendingScrollRestore.current
    if (!container || target == null) return
    const maxScroll = Math.max(0, container.scrollHeight - container.clientHeight)
    container.scrollTop = Math.min(target, maxScroll)
    if (maxScroll >= target) pendingScrollRestore.current = null
  }, [])

  useEffect(() => subscribeReservationRoute((next) => {
    if (!next) return
    const historyActor = window.history.state?.lokaloReservationActor
    if (historyActor && actorKey && historyActor !== actorKey) {
      commitRoute(remembered.current?.route || { view: availableViews[0] || 'today' }, { replace: true })
      return
    }
    routeRef.current = next
    setRoute(next)
  }), [actorKey, availableViews, commitRoute])

  useEffect(() => {
    if (!availableViews.length) return
    const nextView = availableViews.includes(route.view) ? route.view : availableViews[0]
    const mustClearSelection = !canViewContacts && route.reservationId
    const canonical = normalizeReservationRoute({
      ...route,
      view: nextView,
      reservationId: mustClearSelection ? null : route.reservationId,
    })
    const currentHash = readReservationRoute()
    const historyActor = window.history.state?.lokaloReservationActor
    const needsUrl = !currentHash
      || buildReservationHash(canonical) !== window.location.hash
      || (historyActor && actorKey && historyActor !== actorKey)
    if (canonical.view !== route.view || canonical.reservationId !== route.reservationId || needsUrl) {
      commitRoute(canonical, { replace: true })
    }
  }, [actorKey, availableViews, canViewContacts, commitRoute, route])

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
    setSelectionReady(null)
    setSelectionError(null)
    api(`/rezerwacje-stolik/${reservationId}`, 'GET', null, { signal: controller.signal })
      .then((reservation) => {
        if (!current) return
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
        if (!current || error?.name === 'AbortError') return
        setSelectionError(error.message || 'Nie udało się otworzyć wskazanej rezerwacji.')
        if ([403, 404].includes(error?.status)) {
          selectionDates.current.delete(reservationId)
          patchRoute({ reservationId: null }, { replace: true })
        }
      })
    return () => {
      current = false
      controller.abort()
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
    if (routeRef.current.reservationId) selectionDates.current.delete(routeRef.current.reservationId)
    setSelectionError(null)
    patchRoute({ view, reservationId: null })
  }

  const openReservation = (reservation) => {
    const withDetails = canViewContacts ? reservation.id : null
    if (withDetails) selectionDates.current.set(withDetails, reservation.data)
    commitRoute({
      ...routeRef.current,
      view: 'today',
      date: reservation.data,
      reservationId: withDetails,
    }, { state: withDetails ? { lokaloReservationOverlay: true } : {} })
  }

  const closeReservation = () => {
    if (routeRef.current.reservationId) selectionDates.current.delete(routeRef.current.reservationId)
    setSelectionError(null)
    if (window.history.state?.lokaloReservationOverlay) {
      window.history.back()
      return
    }
    patchRoute({ reservationId: null }, { replace: true })
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
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-muted">Workspace operacyjny</p>
          <h2 className="mt-1 font-display text-2xl font-semibold tracking-tight text-ink">Rezerwacje</h2>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Plan dnia, kalendarz, historia i obsługa gości w jednym miejscu.</p>
        </div>
        <nav className="grid w-full grid-cols-4 gap-1 rounded-xl border border-line bg-white/[0.025] p-1 sm:flex sm:w-auto" aria-label="Widoki rezerwacji">
          {availableViews.map((view) => {
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
            date={route.date}
            onDateChange={(date) => patchRoute({ date, reservationId: null })}
            reservationId={canViewContacts && selectionReady === route.reservationId ? route.reservationId : null}
            onReservationOpen={(reservationId) => {
              selectionDates.current.set(reservationId, route.date)
              patchRoute(
                { reservationId },
                { state: { lokaloReservationOverlay: true } },
              )
            }}
            onReservationClose={closeReservation}
          />
        </section>
      ) : null}

      {availableViews.includes('calendar') && visited.has('calendar') ? (
        <section hidden={safeView !== 'calendar'} inert={safeView !== 'calendar' ? '' : undefined} aria-label="Kalendarz rezerwacji">
          <ReservationsCalendar
            date={route.date}
            mode={route.mode}
            status={route.status}
            active={safeView === 'calendar'}
            canOpenDetails={canViewContacts}
            onContextChange={(patch, options) => patchRoute(patch, options)}
            onOpenDay={(date) => patchRoute({ view: 'today', date, reservationId: null })}
            onOpenReservation={openReservation}
          />
        </section>
      ) : null}

      {availableViews.includes('database') && visited.has('database') ? (
        <section hidden={safeView !== 'database'} inert={safeView !== 'database' ? '' : undefined} aria-label="Baza rezerwacji">
          <ReservationsDatabase
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
            date={route.date}
            onDateChange={(date) => patchRoute({ date, reservationId: null })}
            active={safeView === 'host'}
          />
        </section>
      ) : null}
    </div>
  )
}
