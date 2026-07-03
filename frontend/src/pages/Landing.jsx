import { useState, useEffect, useMemo } from 'react'
import { AnimatedLogo } from '../components/Logo'
import Login from './Login'
import { AnimatePresence } from 'framer-motion'

// Zegar czasu lokalnego w Polsce (Europe/Warsaw), aktualizowany co sekundę.
function usePolandClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  const fmtDate = useMemo(
    () => new Intl.DateTimeFormat('pl-PL', { timeZone: 'Europe/Warsaw', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
    [],
  )
  const fmtTime = useMemo(
    () => new Intl.DateTimeFormat('pl-PL', { timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    [],
  )
  return { data: fmtDate.format(now), czas: fmtTime.format(now) }
}

// Wydzielony zegar — TYLKO ten komponent przerenderowuje się co sekundę, więc
// reszta ekranu (w tym modal logowania) pozostaje stabilna i nie traci fokusu.
function LiveClock() {
  const { data, czas } = usePolandClock()
  return (
    <>
      <div className="font-display text-6xl font-bold leading-none tracking-tight tabular-nums sm:text-7xl md:text-8xl text-ink">
        {czas}
      </div>
      <div className="mt-4 text-base font-medium capitalize text-muted sm:text-lg">{data}</div>
    </>
  )
}

export default function Landing() {
  // ?login&tryb=rejestracja (ze strony ?start „Dołączam do zespołu") → modal
  // logowania otwiera się od razu, już w trybie rejestracji (tryb czyta Login).
  const [showLogin, setShowLogin] = useState(
    () => new URLSearchParams(window.location.search).get('tryb') === 'rejestracja'
  )
  const openLogin = () => setShowLogin(true)

  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden bg-bg">
      {/* Sekcja główna: logo lokalu + zegar + jedyna akcja.
          pt-safe/pb-safe odsuwa treść od notcha iPhone (status bar black-translucent). */}
      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 pb-safe pt-safe text-center">
        <AnimatedLogo className="mb-9 h-24 animate-fade-up sm:h-28" />

        <p className="mb-5 flex animate-fade-up items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted" style={{ animationDelay: '80ms' }}>
          <span className="h-2 w-2 animate-pulse rounded-full bg-success" />
          Czas lokalny — Polska
        </p>

        <div className="animate-fade-up" style={{ animationDelay: '140ms' }}>
          <LiveClock />
        </div>

        <button
          onClick={openLogin}
          className="mt-12 animate-fade-up rounded-full bg-cream px-12 py-4 text-sm font-semibold text-bg transition hover:bg-white active:scale-[0.98]"
          style={{ animationDelay: '200ms' }}
        >
          Zaloguj się
        </button>

        <p className="mt-6 max-w-sm animate-fade-up text-xs leading-relaxed text-muted/80" style={{ animationDelay: '260ms' }}>
          Grafik pracy, dyspozycyjność i powiadomienia. Zaloguj się, aby zarządzać harmonogramem lub zgłosić swoją dyspozycyjność.
        </p>
      </main>

      <AnimatePresence>{showLogin && <Login key="login" onClose={() => setShowLogin(false)} />}</AnimatePresence>
    </div>
  )
}
