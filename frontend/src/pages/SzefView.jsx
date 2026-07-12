import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useBranding } from '../context/BrandingContext'
import { Logo } from '../components/Logo'
import { PushButton } from '../components/PushButton'
import { Icon } from '../lib/icons'
import { Spinner } from '../components/ui/Spinner'
import StolyLive from '../components/tabs/StolyLive'
import RaportGodzin from '../components/tabs/RaportGodzin'
import SzefGrafik from '../components/tabs/SzefGrafik'
import SzefImprezy from '../components/tabs/SzefImprezy'
import Zeszyt from '../components/tabs/Zeszyt'
import Rezerwacje from '../components/tabs/Rezerwacje'
import ReservationsWorkspace from '../components/tabs/ReservationsWorkspace'
import {
  clearReservationRoute,
  navigateReservationRoute,
  readReservationRoute,
  subscribeReservationRoute,
} from '../lib/reservationRoute'
import { readReservationSession, reservationActorKey } from '../lib/reservationSession'

const TABY = [
  { value: 'grafik', label: 'Grafik', permission: 'grafik.podglad', Comp: SzefGrafik },
  { value: 'stoly', label: 'Stoły', permission: 'grafik.podglad', Comp: StolyLive },
  { value: 'zeszyt', label: 'Zeszyt', permission: 'zeszyt.podglad', Comp: Zeszyt },
  { value: 'godziny', label: 'Godziny', permission: 'raporty.podglad', Comp: RaportGodzin },
  { value: 'imprezy', label: 'Imprezy', permission: 'imprezy.podglad', Comp: SzefImprezy },
  { value: 'rezerwacje-podglad', label: 'Rezerwacje (podgląd)', permission: 'rezerwacje.podglad', Comp: Rezerwacje, legacyReservation: true },
  {
    value: 'rezerwacje',
    label: 'Rezerwacje',
    anyPermission: ['rezerwacje.operacje', 'rezerwacje.host'],
    Comp: ReservationsWorkspace,
    wide: true,
    reservationWorkspace: true,
  },
]

// Panel „Szef" — oversight tylko do odczytu: kto pracuje + godziny (Raport godzin),
// opublikowany grafik, kalendarz imprez. Bez żadnej edycji.
export default function SzefView() {
  const { user, logout, can, uprawnieniaReady = true } = useAuth()
  const reservationActor = reservationActorKey(user)
  const { nazwa_lokalu } = useBranding()
  const [widok, setWidok] = useState(() => readReservationRoute()
    ? 'rezerwacje'
    : 'grafik')
  const imie = user?.imie || user?.login
  const maOperacyjnyDostepRezerwacji = can('rezerwacje.operacje') || can('rezerwacje.host')
  const widoczneTaby = useMemo(() => TABY.filter((tab) => {
    if (tab.legacyReservation && maOperacyjnyDostepRezerwacji) return false
    if (tab.anyPermission) return tab.anyPermission.some((permission) => can(permission))
    return can(tab.permission)
  }), [can, maOperacyjnyDostepRezerwacji])
  const maWorkspaceRezerwacji = widoczneTaby.some((tab) => tab.reservationWorkspace)
  const maInnyWorkspaceSzefa = widoczneTaby.some((tab) => !tab.reservationWorkspace)
  const czyRecepcja = maWorkspaceRezerwacji && !maInnyWorkspaceSzefa
  const aktywnyTab = widoczneTaby.find((tab) => tab.value === widok)
    || widoczneTaby.find((tab) => tab.value === 'grafik')
    || widoczneTaby[0]
  const Active = aktywnyTab?.Comp

  useEffect(() => {
    if (!uprawnieniaReady || !aktywnyTab || widok === aktywnyTab.value) return
    setWidok(aktywnyTab.value)
  }, [aktywnyTab, uprawnieniaReady, widok])

  useEffect(() => subscribeReservationRoute((reservationRoute) => {
    if (reservationRoute) {
      setWidok('rezerwacje')
      return
    }
    const restored = window.history.state?.lokaloManagerTab
    if (restored) setWidok(restored)
  }), [])

  useEffect(() => {
    if (!uprawnieniaReady || !readReservationRoute() || maWorkspaceRezerwacji) return
    const fallback = aktywnyTab?.value || widoczneTaby[0]?.value || 'grafik'
    clearReservationRoute({ replace: true, state: { lokaloManagerTab: fallback } })
  }, [aktywnyTab, maWorkspaceRezerwacji, uprawnieniaReady, widoczneTaby])

  const selectView = (value) => {
    if (value === 'rezerwacje') {
      if (!readReservationRoute()) {
        window.history.replaceState({
          ...(window.history.state || {}),
          lokaloManagerTab: widok,
        }, '', window.location.href)
        navigateReservationRoute(
          readReservationSession(user)?.route
            || { view: can('rezerwacje.operacje') ? 'today' : 'host' },
          {
            state: {
              lokaloManagerTab: 'rezerwacje',
              ...(reservationActor ? { lokaloReservationActor: reservationActor } : {}),
            },
          },
        )
      }
    } else if (readReservationRoute()) {
      clearReservationRoute({ state: { lokaloManagerTab: value } })
    } else {
      window.history.replaceState({
        ...(window.history.state || {}),
        lokaloManagerTab: value,
      }, '', window.location.href)
    }
    setWidok(value)
  }

  return (
    <div className="relative min-h-dvh bg-bg">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <header className="relative z-10 flex items-center justify-between border-b border-white/[0.06] bg-bg/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Logo className="h-8" variant="gradient" />
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">{nazwa_lokalu}</h1>
            <p className="text-xs text-muted">{czyRecepcja ? 'Recepcja / Host' : 'Panel szefa'}{imie ? ` · ${imie}` : ''}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PushButton />
          <button
            type="button"
            onClick={logout}
            className="flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
            aria-label="Wyloguj"
          >
            <Icon name="logout" className="h-4 w-4" />
            <span className="hidden sm:inline">Wyloguj</span>
          </button>
        </div>
      </header>

      <main className={`relative z-10 mx-auto w-full px-4 py-6 pb-safe md:py-10 ${aktywnyTab?.wide ? 'max-w-7xl' : 'max-w-5xl'}`}>
        {!uprawnieniaReady ? (
          <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-line bg-white/[0.02]" role="status" aria-label="Wczytywanie dostępu">
            <Spinner className="h-5 w-5 text-muted motion-reduce:animate-none" />
            <p className="text-sm text-muted">Przygotowuję Twój zakres pracy…</p>
          </div>
        ) : widoczneTaby.length === 0 ? (
          <div className="rounded-2xl border border-line bg-white/[0.02] px-5 py-10 text-center">
            <h2 className="font-display text-lg font-semibold text-ink">Brak przydzielonych widoków</h2>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted">
              Administrator może włączyć potrzebne obszary w ustawieniach konta.
            </p>
          </div>
        ) : (
          <>
            <nav className="mb-6 flex gap-2 overflow-x-auto pb-1" aria-label={czyRecepcja ? 'Widoki recepcji' : 'Widoki szefa'}>
              {widoczneTaby.map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  onClick={() => selectView(tab.value)}
                  aria-current={widok === tab.value ? 'page' : undefined}
                  className={`min-h-11 shrink-0 rounded-xl px-4 py-2 text-sm font-semibold transition active:scale-[0.98] ${
                    widok === tab.value ? 'bg-mint text-bg' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
                  }`}
                  style={{ WebkitTapHighlightColor: 'transparent' }}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            {Active && (
              <div key={aktywnyTab.value} className="animate-tab-in">
                {aktywnyTab.value === 'zeszyt' ? (
                  <Active readOnly endpoint="/szef/zeszyt" />
                ) : aktywnyTab.value === 'grafik' ? (
                  <Active onOpenLive={() => selectView('stoly')} />
                ) : (
                  <Active />
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
