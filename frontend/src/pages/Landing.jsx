import { useState, useEffect, useMemo } from 'react'
import { Icon } from '../lib/icons'
import Login from './Login'

const NAV = ['Home', 'About', 'Gallery', 'Event', 'Contact']

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

export default function Landing() {
  const [showLogin, setShowLogin] = useState(false)
  const { data, czas } = usePolandClock()
  const openLogin = () => setShowLogin(true)

  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden bg-bg">
      {/* Subtelne pastelowe poświaty w tle */}
      <div aria-hidden className="pointer-events-none absolute -left-40 -top-40 h-[28rem] w-[28rem] rounded-full bg-page-glow opacity-[0.10] blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-40 -right-32 h-96 w-96 rounded-full bg-mint opacity-[0.06] blur-3xl" />

      {/* Pasek nawigacji — wszystkie pozycje otwierają logowanie */}
      <header className="relative z-10 flex items-center justify-between px-6 py-6 md:px-12">
        <button onClick={openLogin} className="flex items-center gap-3" aria-label="Grafik Pracy — zaloguj">
          <span className="grid h-10 w-10 place-items-center rounded-full border border-white/15 text-ink">
            <Icon name="sparkles" className="h-5 w-5" />
          </span>
          <span className="font-display text-lg font-bold tracking-tight text-ink">
            Grafik<span className="text-gradient">Pracy</span>
          </span>
        </button>

        <nav className="hidden items-center gap-8 lg:flex">
          {NAV.map((item) => (
            <button
              key={item}
              onClick={openLogin}
              className="text-xs font-semibold uppercase tracking-[0.15em] text-muted transition hover:text-ink"
            >
              {item}
            </button>
          ))}
        </nav>

        <button
          onClick={openLogin}
          className="rounded-lg border border-white/15 px-5 py-2 text-xs font-semibold uppercase tracking-[0.15em] text-ink transition hover:bg-white/5"
        >
          Login
        </button>
      </header>

      {/* Sekcja główna: zegar + jedyna akcja */}
      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-6 text-center">
        <p className="mb-5 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-muted">
          <span className="h-2 w-2 animate-pulse rounded-full bg-success" />
          Czas lokalny — Polska
        </p>

        <div className="font-display text-6xl font-bold leading-none tracking-tight text-gradient tabular-nums sm:text-7xl md:text-8xl">
          {czas}
        </div>
        <div className="mt-4 text-base font-medium capitalize text-muted sm:text-lg">{data}</div>

        <button
          onClick={openLogin}
          className="mt-12 rounded-full bg-cream px-12 py-4 text-sm font-bold uppercase tracking-[0.2em] text-bg shadow-cta transition hover:brightness-[1.03] active:scale-[0.98]"
        >
          Zaloguj się
        </button>

        <p className="mt-6 max-w-sm text-xs leading-relaxed text-muted/80">
          System grafików pracy. Zaloguj się, aby zarządzać harmonogramem lub zgłosić swoją dyspozycyjność.
        </p>
      </main>

      {showLogin && <Login onClose={() => setShowLogin(false)} />}
    </div>
  )
}
