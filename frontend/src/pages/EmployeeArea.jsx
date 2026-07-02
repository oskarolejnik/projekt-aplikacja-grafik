import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { useData } from '../context/DataContext'
import { useBranding } from '../context/BrandingContext'
import { useToast } from '../components/ui/Toast'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { PushButton } from '../components/PushButton'
import EmployeeAvailability from './EmployeeAvailability'
import EmployeeSchedule from './EmployeeSchedule'
import EmployeeHours from './EmployeeHours'
import EmployeeGielda from './EmployeeGielda'
import EmployeeOgloszenia from './EmployeeOgloszenia'
import Rezerwacje from '../components/tabs/Rezerwacje'
import KuchniaImprezy from '../components/tabs/KuchniaImprezy'
import TechSprzatanie from '../components/tabs/TechSprzatanie'
import TechZamowienia from '../components/tabs/TechZamowienia'

const LAST_SEEN_KEY = 'grafik_ostatni_grafik'

// Powłoka obszaru pracownika: wspólny nagłówek + przełącznik dwóch widoków
// („Moja dyspozycyjność" / „Mój grafik"), powiadomienia i przycisk push. Mobile-first.
export default function EmployeeArea() {
  const { user, logout } = useAuth()
  const { biezacy } = useData()
  const { nazwa_lokalu } = useBranding()
  const { toast } = useToast()
  const jestKuchnia = user?.rola === 'kuchnia'   // kuchnia: bez Dyspozycyjności
  const jestTechniczny = user?.dzial === 'techniczny'  // techniczni: Sprzątanie + Godziny (bez grafiku/dyspo)
  const jestSprzataczka = !!user?.sprzataczka          // sprzątaczka: dodatkowo zakładka Zamówienia
  const [widok, setWidok] = useState(jestTechniczny ? 'sprzatanie' : jestKuchnia ? 'grafik' : 'dyspozycyjnosc')
  const [nowyGrafik, setNowyGrafik] = useState(false)
  const [nieprzeczytaneOgl, setNieprzeczytaneOgl] = useState(0)

  const imie = user?.imie || user?.login

  // Licznik nieprzeczytanych ogłoszeń → odznaka na zakładce „Ogłoszenia".
  useEffect(() => {
    api('/me/ogloszenia').then((r) => setNieprzeczytaneOgl(r.nieprzeczytane || 0)).catch(() => {})
  }, [])

  // Wykryj nowo udostępniony grafik -> baner + odznaka na zakładce „Mój grafik".
  // (Techniczni nie mają grafiku — pomijamy zapytanie.)
  useEffect(() => {
    if (jestTechniczny) return
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
  }, [biezacy, toast, jestTechniczny])

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
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <header className="relative z-10 flex items-center justify-between border-b border-white/[0.06] bg-bg/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Logo className="h-8" variant="gradient" />
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">{nazwa_lokalu}</h1>
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
            Imprezy). Obsługa: 5 (Dyspo + te same co kuchnia). Techniczni: Sprzątanie + Godziny.
            Rezerwacje i Imprezy są wspólne (bez danych klienta). */}
        <div className="mb-6 flex gap-2 overflow-x-auto pb-1">
          {(jestTechniczny
            ? [
                { value: 'sprzatanie', label: 'Sprzątanie' },
                ...(jestSprzataczka ? [{ value: 'zamowienia', label: 'Zamówienia' }] : []),
                { value: 'godziny', label: 'Godziny' },
                { value: 'ogloszenia', label: 'Ogłoszenia', badge: nieprzeczytaneOgl > 0 },
              ]
            : jestKuchnia
            ? [
                { value: 'grafik', label: 'Grafik', badge: nowyGrafik },
                { value: 'gielda', label: 'Giełda' },
                { value: 'godziny', label: 'Godziny' },
                { value: 'rezerwacje', label: 'Rezerwacje' },
                { value: 'imprezy', label: 'Imprezy' },
                { value: 'ogloszenia', label: 'Ogłoszenia', badge: nieprzeczytaneOgl > 0 },
              ]
            : [
                { value: 'dyspozycyjnosc', label: 'Dyspo' },
                { value: 'grafik', label: 'Grafik', badge: nowyGrafik },
                { value: 'gielda', label: 'Giełda' },
                { value: 'godziny', label: 'Godziny' },
                { value: 'rezerwacje', label: 'Rezerwacje' },
                { value: 'imprezy', label: 'Imprezy' },
                { value: 'ogloszenia', label: 'Ogłoszenia', badge: nieprzeczytaneOgl > 0 },
              ]
          ).map((t) => (
            <button
              key={t.value}
              onClick={() => zmienWidok(t.value)}
              className={`relative shrink-0 rounded-xl px-4 py-2 text-sm font-semibold transition active:scale-[0.98] ${
                widok === t.value ? 'bg-mint text-bg' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
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
          {widok === 'gielda' && <EmployeeGielda />}
          {widok === 'ogloszenia' && <EmployeeOgloszenia onZmiana={setNieprzeczytaneOgl} />}
          {widok === 'godziny' && <EmployeeHours />}
          {widok === 'rezerwacje' && <Rezerwacje />}
          {widok === 'imprezy' && <KuchniaImprezy />}
          {widok === 'sprzatanie' && <TechSprzatanie />}
          {widok === 'zamowienia' && <TechZamowienia />}
        </div>
      </main>
    </div>
  )
}
