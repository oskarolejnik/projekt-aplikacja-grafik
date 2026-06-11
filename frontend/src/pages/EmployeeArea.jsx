import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { useData } from '../context/DataContext'
import { useToast } from '../components/ui/Toast'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { PushButton } from '../components/PushButton'
import EmployeeAvailability from './EmployeeAvailability'
import EmployeeSchedule from './EmployeeSchedule'
import EmployeeHours from './EmployeeHours'
import Rezerwacje from '../components/tabs/Rezerwacje'
import KuchniaImprezy from '../components/tabs/KuchniaImprezy'

const LAST_SEEN_KEY = 'grafik_ostatni_grafik'

// Powłoka obszaru pracownika: wspólny nagłówek + przełącznik dwóch widoków
// („Moja dyspozycyjność" / „Mój grafik"), powiadomienia i przycisk push. Mobile-first.
export default function EmployeeArea() {
  const { user, logout } = useAuth()
  const { biezacy } = useData()
  const { toast } = useToast()
  const jestKuchnia = user?.rola === 'kuchnia'   // kuchnia: tylko Grafik + Godziny (bez Dyspozycyjności)
  const [widok, setWidok] = useState(jestKuchnia ? 'grafik' : 'dyspozycyjnosc')
  const [nowyGrafik, setNowyGrafik] = useState(false)

  const imie = user?.imie || user?.login

  // Wykryj nowo udostępniony grafik -> baner + odznaka na zakładce „Mój grafik".
  useEffect(() => {
    let off = false
    const [s, e] = biezacy.split('|')
    api(`/me/grafik?start=${s}&end=${e}`)
      .then((r) => {
        if (off) return
        if (r.opublikowany && r.opublikowano_at && localStorage.getItem(LAST_SEEN_KEY) !== r.opublikowano_at) {
          setNowyGrafik(true)
          toast('Nowy grafik został udostępniony!', 'success')
        }
      })
      .catch(() => {})
    return () => {
      off = true
    }
  }, [biezacy, toast])

  const oznaczWidziany = useCallback((ts) => {
    localStorage.setItem(LAST_SEEN_KEY, ts)
    setNowyGrafik(false)
  }, [])

  const zmienWidok = (v) => {
    setWidok(v)
    if (v === 'grafik') setNowyGrafik(false)
  }

  return (
    <div className="relative min-h-dvh bg-bg">
      <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-96 w-96 rounded-full bg-page-glow opacity-[0.07] blur-2xl transform-gpu" />

      <header className="relative z-10 flex items-center justify-between border-b border-line bg-bg-2/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur">
        <div className="flex items-center gap-3">
          <Logo className="h-8" variant="gradient" />
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">Rajcula</h1>
            <p className="text-xs text-muted">Cześć, {imie}!</p>
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

      <main className="relative z-10 mx-auto w-full max-w-3xl px-4 py-6 pb-safe md:py-10">
        {/* Nawigacja zakładek — przewijany pasek. Kuchnia: 4 (Grafik, Godziny, Rezerwacje,
            Imprezy). Obsługa: 5 (Dyspo + te same co kuchnia). Rezerwacje i Imprezy są wspólne
            (bez danych klienta). */}
        <div className="mb-6 flex gap-2 overflow-x-auto pb-1">
          {(jestKuchnia
            ? [
                { value: 'grafik', label: 'Grafik', badge: nowyGrafik },
                { value: 'godziny', label: 'Godziny' },
                { value: 'rezerwacje', label: 'Rezerwacje' },
                { value: 'imprezy', label: 'Imprezy' },
              ]
            : [
                { value: 'dyspozycyjnosc', label: 'Dyspo' },
                { value: 'grafik', label: 'Grafik', badge: nowyGrafik },
                { value: 'godziny', label: 'Godziny' },
                { value: 'rezerwacje', label: 'Rezerwacje' },
                { value: 'imprezy', label: 'Imprezy' },
              ]
          ).map((t) => (
            <button
              key={t.value}
              onClick={() => zmienWidok(t.value)}
              className={`relative shrink-0 rounded-xl px-4 py-2 text-sm font-bold transition active:scale-[0.97] ${
                widok === t.value ? 'bg-accent-gradient text-bg shadow-glow' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
              }`}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              {t.label}
              {t.badge && <span className="absolute right-1.5 top-1.5 h-2.5 w-2.5 rounded-full bg-coral ring-2 ring-bg" />}
            </button>
          ))}
        </div>

        {/* Treść zakładki: reveal na czystym CSS (kompozytor; brak rAF-stuttera). */}
        <div key={widok} className="animate-tab-in">
          {widok === 'dyspozycyjnosc' && <EmployeeAvailability />}
          {widok === 'grafik' && <EmployeeSchedule onSeen={oznaczWidziany} />}
          {widok === 'godziny' && <EmployeeHours />}
          {widok === 'rezerwacje' && <Rezerwacje />}
          {widok === 'imprezy' && <KuchniaImprezy />}
        </div>
      </main>
    </div>
  )
}
