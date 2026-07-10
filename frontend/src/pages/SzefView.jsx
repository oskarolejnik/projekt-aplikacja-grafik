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

const TABY = [
  { value: 'grafik', label: 'Grafik', permission: 'grafik.podglad', Comp: SzefGrafik },
  { value: 'stoly', label: 'Stoły', permission: 'grafik.podglad', Comp: StolyLive },
  { value: 'zeszyt', label: 'Zeszyt', permission: 'zeszyt.podglad', Comp: Zeszyt },
  { value: 'godziny', label: 'Godziny', permission: 'raporty.podglad', Comp: RaportGodzin },
  { value: 'imprezy', label: 'Imprezy', permission: 'imprezy.podglad', Comp: SzefImprezy },
  { value: 'rezerwacje', label: 'Rezerwacje', permission: 'rezerwacje.podglad', Comp: Rezerwacje },
]

// Panel „Szef" — oversight tylko do odczytu: kto pracuje + godziny (Raport godzin),
// opublikowany grafik, kalendarz imprez. Bez żadnej edycji.
export default function SzefView() {
  const { user, logout, can, uprawnieniaReady = true } = useAuth()
  const { nazwa_lokalu } = useBranding()
  const [widok, setWidok] = useState('grafik')
  const imie = user?.imie || user?.login
  const widoczneTaby = useMemo(() => TABY.filter((tab) => can(tab.permission)), [can])
  const aktywnyTab = widoczneTaby.find((tab) => tab.value === widok)
    || widoczneTaby.find((tab) => tab.value === 'grafik')
    || widoczneTaby[0]
  const Active = aktywnyTab?.Comp

  useEffect(() => {
    if (!uprawnieniaReady || !aktywnyTab || widok === aktywnyTab.value) return
    setWidok(aktywnyTab.value)
  }, [aktywnyTab, uprawnieniaReady, widok])

  return (
    <div className="relative min-h-dvh bg-bg">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <header className="relative z-10 flex items-center justify-between border-b border-white/[0.06] bg-bg/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Logo className="h-8" variant="gradient" />
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">{nazwa_lokalu}</h1>
            <p className="text-xs text-muted">Panel szefa{imie ? ` · ${imie}` : ''}</p>
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

      <main className="relative z-10 mx-auto w-full max-w-5xl px-4 py-6 pb-safe md:py-10">
        {!uprawnieniaReady ? (
          <div className="grid min-h-48 place-items-center" role="status" aria-label="Wczytywanie dostępu">
            <Spinner className="h-6 w-6 text-muted" />
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
            <nav className="mb-6 flex gap-2 overflow-x-auto pb-1" aria-label="Widoki szefa">
              {widoczneTaby.map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  onClick={() => setWidok(tab.value)}
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
                  <Active onOpenLive={() => setWidok('stoly')} />
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
