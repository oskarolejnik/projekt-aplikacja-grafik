import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import StolyLive from '../components/tabs/StolyLive'
import RaportGodzin from '../components/tabs/RaportGodzin'
import SzefGrafik from '../components/tabs/SzefGrafik'
import SzefImprezy from '../components/tabs/SzefImprezy'
import Rezerwacje from '../components/tabs/Rezerwacje'

const TABY = [
  { value: 'stoly', label: 'Stoły' },
  { value: 'godziny', label: 'Godziny' },
  { value: 'grafik', label: 'Grafik' },
  { value: 'imprezy', label: 'Imprezy' },
  { value: 'rezerwacje', label: 'Rezerwacje' },
]

// Panel „Szef" — oversight tylko do odczytu: kto pracuje + godziny (Raport godzin),
// opublikowany grafik, kalendarz imprez. Bez żadnej edycji.
export default function SzefView() {
  const { user, logout } = useAuth()
  const [widok, setWidok] = useState('stoly')
  const imie = user?.imie || user?.login

  return (
    <div className="relative min-h-dvh bg-bg">
      <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-96 w-96 rounded-full bg-page-glow opacity-[0.07] blur-2xl transform-gpu" />

      <header className="relative z-10 flex items-center justify-between border-b border-line bg-bg-2/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur">
        <div className="flex items-center gap-3">
          <Logo className="h-8" variant="gradient" />
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">Rajcula</h1>
            <p className="text-xs text-muted">Panel szefa{imie ? ` · ${imie}` : ''}</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
        >
          <Icon name="logout" className="h-4 w-4" />
          <span className="hidden sm:inline">Wyloguj</span>
        </button>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-5xl px-4 py-6 pb-safe md:py-10">
        {/* Przewijany pasek zakładek (mieści dowolną liczbę pozycji na mobile). */}
        <div className="mb-6 flex gap-2 overflow-x-auto pb-1">
          {TABY.map((t) => (
            <button
              key={t.value}
              onClick={() => setWidok(t.value)}
              className={`shrink-0 rounded-xl px-4 py-2 text-sm font-bold transition active:scale-[0.97] ${
                widok === t.value ? 'bg-accent-gradient text-bg shadow-glow' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
              }`}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div key={widok} className="animate-tab-in">
          {widok === 'stoly' && <StolyLive />}
          {widok === 'godziny' && <RaportGodzin />}
          {widok === 'grafik' && <SzefGrafik />}
          {widok === 'imprezy' && <SzefImprezy />}
          {widok === 'rezerwacje' && <Rezerwacje />}
        </div>
      </main>
    </div>
  )
}
