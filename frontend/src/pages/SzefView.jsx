import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useBranding } from '../context/BrandingContext'
import { Logo } from '../components/Logo'
import { PushButton } from '../components/PushButton'
import { Icon } from '../lib/icons'
import StolyLive from '../components/tabs/StolyLive'
import RaportGodzin from '../components/tabs/RaportGodzin'
import SzefGrafik from '../components/tabs/SzefGrafik'
import SzefImprezy from '../components/tabs/SzefImprezy'
import Zeszyt from '../components/tabs/Zeszyt'
import Rezerwacje from '../components/tabs/Rezerwacje'

const TABY = [
  { value: 'stoly', label: 'Stoły' },
  { value: 'zeszyt', label: 'Zeszyt' },
  { value: 'godziny', label: 'Godziny' },
  { value: 'grafik', label: 'Grafik' },
  { value: 'imprezy', label: 'Imprezy' },
  { value: 'rezerwacje', label: 'Rezerwacje' },
]

// Panel „Szef" — oversight tylko do odczytu: kto pracuje + godziny (Raport godzin),
// opublikowany grafik, kalendarz imprez. Bez żadnej edycji.
export default function SzefView() {
  const { user, logout } = useAuth()
  const { nazwa_lokalu } = useBranding()
  const [widok, setWidok] = useState('stoly')
  const imie = user?.imie || user?.login

  return (
    <div className="relative min-h-dvh bg-bg">
      <header className="relative z-10 flex items-center justify-between border-b border-line bg-bg-2/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur">
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
            onClick={logout}
            className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
          >
            <Icon name="logout" className="h-4 w-4" />
            <span className="hidden sm:inline">Wyloguj</span>
          </button>
        </div>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-5xl px-4 py-6 pb-safe md:py-10">
        {/* Przewijany pasek zakładek (mieści dowolną liczbę pozycji na mobile). */}
        <div className="mb-6 flex gap-2 overflow-x-auto pb-1">
          {TABY.map((t) => (
            <button
              key={t.value}
              onClick={() => setWidok(t.value)}
              className={`shrink-0 rounded-xl px-4 py-2 text-sm font-semibold transition active:scale-[0.98] ${
                widok === t.value ? 'bg-mint text-bg' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
              }`}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div key={widok} className="animate-tab-in">
          {widok === 'stoly' && <StolyLive />}
          {widok === 'zeszyt' && <Zeszyt readOnly endpoint="/szef/zeszyt" />}
          {widok === 'godziny' && <RaportGodzin />}
          {widok === 'grafik' && <SzefGrafik />}
          {widok === 'imprezy' && <SzefImprezy />}
          {widok === 'rezerwacje' && <Rezerwacje />}
        </div>
      </main>
    </div>
  )
}
