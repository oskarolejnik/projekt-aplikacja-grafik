import { useState, useEffect, useCallback, useId, useRef } from 'react'
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

// Powłoka obszaru pracownika: najpierw odpowiedź na „kiedy pracuję?”, potem
// bieżące informacje i dopiero zadania okazjonalne. Mobile-first.
export default function EmployeeArea() {
  const { user, logout } = useAuth()
  const { biezacy } = useData()
  const { nazwa_lokalu } = useBranding()
  const { toast } = useToast()
  const jestKuchnia = user?.rola === 'kuchnia'   // kuchnia: bez Dyspozycyjności
  const jestTechniczny = user?.dzial === 'techniczny'  // techniczni: Sprzątanie + Godziny (bez grafiku/dyspo)
  const jestSprzataczka = !!user?.sprzataczka          // sprzątaczka: dodatkowo zakładka Zamówienia
  const [widok, setWidok] = useState(jestTechniczny ? 'sprzatanie' : 'grafik')
  const [nowyGrafik, setNowyGrafik] = useState(false)
  const [nieprzeczytaneOgl, setNieprzeczytaneOgl] = useState(0)
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false)
  const mobileMoreButtonRef = useRef(null)
  const mobileMoreDialogRef = useRef(null)
  const mobileMoreTitleId = useId()

  const imie = user?.imie || user?.login
  const widoki = jestTechniczny
    ? [
        { value: 'sprzatanie', label: 'Sprzątanie', icon: 'check' },
        ...(jestSprzataczka ? [{ value: 'zamowienia', label: 'Zamówienia', icon: 'clipboard' }] : []),
        { value: 'godziny', label: 'Godziny', icon: 'clock' },
      ]
    : jestKuchnia
    ? [
        { value: 'grafik', label: 'Grafik', icon: 'calendar', badge: nowyGrafik },
        { value: 'godziny', label: 'Godziny', icon: 'clock' },
        { value: 'gielda', label: 'Giełda', icon: 'users' },
        { value: 'rezerwacje', label: 'Rezerwacje', icon: 'calendar' },
        { value: 'imprezy', label: 'Imprezy', icon: 'bell' },
      ]
    : [
        { value: 'grafik', label: 'Grafik', icon: 'calendar', badge: nowyGrafik },
        { value: 'godziny', label: 'Godziny', icon: 'clock' },
        { value: 'dyspozycyjnosc', label: 'Dyspo', icon: 'check' },
        { value: 'gielda', label: 'Giełda', icon: 'users' },
        { value: 'rezerwacje', label: 'Rezerwacje', icon: 'calendar' },
        { value: 'imprezy', label: 'Imprezy', icon: 'bell' },
      ]
  const glowneWidoki = widoki.slice(0, 3)
  const pozostaleWidoki = widoki.slice(3)

  // Licznik nieprzeczytanych ogłoszeń → odznaka przy skrócie w nagłówku.
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

  // Po obrocie urządzenia lub poszerzeniu okna arkusz mobilny przestaje być
  // dostępny wizualnie, więc zamykamy go także logicznie i zwalniamy body scroll.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const desktop = window.matchMedia('(min-width: 768px)')
    const onBreakpoint = (event) => {
      if (event.matches) setMobileMoreOpen(false)
    }
    if (desktop.addEventListener) desktop.addEventListener('change', onBreakpoint)
    else desktop.addListener?.(onBreakpoint)
    return () => {
      if (desktop.removeEventListener) desktop.removeEventListener('change', onBreakpoint)
      else desktop.removeListener?.(onBreakpoint)
    }
  }, [])

  // Mobilny arkusz zachowuje fokus w środku, zamyka się klawiszem Escape
  // i po zamknięciu oddaje fokus do przycisku „Więcej”.
  useEffect(() => {
    if (!mobileMoreOpen) return
    const dialog = mobileMoreDialogRef.current
    const poprzedniOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const focusable = () => Array.from(dialog?.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])') || [])
    focusable()[0]?.focus()

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setMobileMoreOpen(false)
        return
      }
      if (event.key !== 'Tab') return
      const elementy = focusable()
      if (elementy.length === 0) return
      const first = elementy[0]
      const last = elementy[elementy.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = poprzedniOverflow
      mobileMoreButtonRef.current?.focus()
    }
  }, [mobileMoreOpen])

  const zmienWidok = (v) => {
    setWidok(v)
    setMobileMoreOpen(false)
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
            type="button"
            onClick={() => zmienWidok('ogloszenia')}
            aria-label={nieprzeczytaneOgl > 0
              ? `Ogłoszenia, ${nieprzeczytaneOgl} nieprzeczytane`
              : 'Ogłoszenia'}
            aria-current={widok === 'ogloszenia' ? 'page' : undefined}
            className={`relative grid min-h-11 min-w-11 place-items-center rounded-xl border transition active:scale-[0.98] ${
              widok === 'ogloszenia'
                ? 'border-mint/50 bg-mint/15 text-mint'
                : 'border-line bg-white/[0.04] text-muted hover:text-ink'
            }`}
          >
            <Icon name="megaphone" className="h-5 w-5" />
            {nieprzeczytaneOgl > 0 && (
              <span aria-hidden className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-coral ring-2 ring-bg" />
            )}
          </button>
          <button
            type="button"
            onClick={logout}
            aria-label="Wyloguj"
            className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
          >
            <Icon name="logout" className="h-4 w-4" />
            <span className="hidden sm:inline">Wyloguj</span>
          </button>
        </div>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-3xl px-4 py-6 pb-[calc(6.5rem+env(safe-area-inset-bottom))] md:py-10 md:pb-10">
        {/* Nawigacja: najczęstsze pytania najpierw; ogłoszenia są pod skrótem w nagłówku.
            Rezerwacje i imprezy zostają dostępne pracownikowi, lecz nie konkurują z grafikiem. */}
        <nav aria-label="Widoki pracownika" className="mb-6 hidden gap-2 overflow-x-auto pb-1 md:flex">
          {widoki.map((t) => (
            <button
              type="button"
              key={t.value}
              onClick={() => zmienWidok(t.value)}
              aria-current={widok === t.value ? 'page' : undefined}
              className={`relative min-h-11 shrink-0 rounded-xl px-4 py-2 text-sm font-semibold transition active:scale-[0.98] ${
                widok === t.value ? 'bg-mint text-bg' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
              }`}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              {t.label}
              {t.badge && <span className="absolute right-1.5 top-1.5 h-2.5 w-2.5 rounded-full bg-coral ring-2 ring-bg" />}
            </button>
          ))}
        </nav>

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

      <nav
        aria-label="Główna nawigacja mobilna"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-white/[0.08] bg-bg/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
      >
        <div className="mx-auto flex w-full max-w-3xl px-2 pt-1.5">
          {glowneWidoki.map((t) => (
            <button
              type="button"
              key={t.value}
              onClick={() => zmienWidok(t.value)}
              aria-current={widok === t.value ? 'page' : undefined}
              className={`relative flex min-h-[3.75rem] min-w-11 flex-1 flex-col items-center justify-center gap-1 rounded-xl px-1 py-1.5 text-xs font-semibold transition active:scale-[0.98] ${
                widok === t.value ? 'text-mint' : 'text-muted'
              }`}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              <span className={`relative grid h-7 min-w-10 place-items-center rounded-full px-2 ${widok === t.value ? 'bg-mint/15' : ''}`}>
                <Icon name={t.icon} className="h-5 w-5" />
                {t.badge && <span aria-hidden className="absolute right-0 top-0 h-2.5 w-2.5 rounded-full bg-coral ring-2 ring-bg" />}
              </span>
              <span>{t.label}</span>
            </button>
          ))}
          {pozostaleWidoki.length > 0 && (
            <button
              ref={mobileMoreButtonRef}
              type="button"
              onClick={() => setMobileMoreOpen(true)}
              aria-expanded={mobileMoreOpen}
              aria-controls="employee-mobile-more"
              aria-current={pozostaleWidoki.some((t) => t.value === widok) ? 'page' : undefined}
              className={`flex min-h-[3.75rem] min-w-11 flex-1 flex-col items-center justify-center gap-1 rounded-xl px-1 py-1.5 text-xs font-semibold transition active:scale-[0.98] ${
                pozostaleWidoki.some((t) => t.value === widok) ? 'text-mint' : 'text-muted'
              }`}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              <span className={`grid h-7 min-w-10 place-items-center rounded-full px-2 ${pozostaleWidoki.some((t) => t.value === widok) ? 'bg-mint/15' : ''}`}>
                <Icon name="menu" className="h-5 w-5" />
              </span>
              <span>Więcej</span>
            </button>
          )}
        </div>
      </nav>

      {mobileMoreOpen && pozostaleWidoki.length > 0 && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div aria-hidden className="absolute inset-0 bg-black/65" onClick={() => setMobileMoreOpen(false)} />
          <section
            ref={mobileMoreDialogRef}
            id="employee-mobile-more"
            role="dialog"
            aria-modal="true"
            aria-labelledby={mobileMoreTitleId}
            className="material absolute inset-x-0 bottom-0 max-h-[75dvh] overflow-y-auto rounded-b-none rounded-t-2xl border-b-0 p-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 id={mobileMoreTitleId} className="font-display text-lg font-semibold text-ink">Więcej widoków</h2>
              <button
                type="button"
                onClick={() => setMobileMoreOpen(false)}
                className="grid min-h-11 min-w-11 place-items-center rounded-xl text-muted transition hover:bg-white/[0.06] hover:text-ink"
                aria-label="Zamknij więcej widoków"
              >
                <Icon name="close" className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-1">
              {pozostaleWidoki.map((t) => (
                <button
                  type="button"
                  key={t.value}
                  onClick={() => zmienWidok(t.value)}
                  aria-current={widok === t.value ? 'page' : undefined}
                  className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition active:scale-[0.99] ${
                    widok === t.value ? 'bg-mint/15 text-mint' : 'text-ink hover:bg-white/[0.06]'
                  }`}
                >
                  <Icon name={t.icon} className="h-5 w-5 shrink-0" />
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
