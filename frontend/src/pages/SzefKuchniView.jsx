import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '../context/AuthContext'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { useToast } from '../components/ui/Toast'
import { api } from '../lib/api'
import { godzinyHM } from '../lib/format'
import StolyLive from '../components/tabs/StolyLive'
import Rezerwacje from '../components/tabs/Rezerwacje'

const TABY = [
  { value: 'kuchnia', label: 'Kuchnia' },
  { value: 'stoly', label: 'Stoły' },
  { value: 'rezerwacje', label: 'Rezerwacje' },
]

// Godziny pracowników KUCHNI — BEZ wypłat: kto teraz pracuje + ile godzin w miesiącu.
// Dane: GET /api/szefkuchni/godziny?rok=&miesiac= (backend obcina pola finansowe).
function KuchniaGodziny() {
  const { toast } = useToast()
  const dzis = new Date()
  const [rok, setRok] = useState(dzis.getFullYear())
  const [miesiac, setMiesiac] = useState(dzis.getMonth() + 1) // 1-12
  const [dane, setDane] = useState(null)
  const [loading, setLoading] = useState(true)

  const etykietaMiesiaca = useMemo(
    () => new Intl.DateTimeFormat('pl-PL', { month: 'long', year: 'numeric' }).format(new Date(rok, miesiac - 1, 1)),
    [rok, miesiac],
  )

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setDane(await api(`/szefkuchni/godziny?rok=${rok}&miesiac=${miesiac}`))
    } catch (e) {
      if (!silent) { toast(e.message, 'error'); setDane(null) }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [rok, miesiac, toast])

  useEffect(() => { load() }, [load])

  // Live: ciche odświeżanie co 20 s (bez spinnera), gdy karta jest widoczna.
  useEffect(() => {
    const id = setInterval(() => { if (document.visibilityState === 'visible') load(true) }, 20000)
    return () => clearInterval(id)
  }, [load])

  const przesunMiesiac = (delta) => {
    let m = miesiac + delta
    let r = rok
    if (m < 1) { m = 12; r -= 1 }
    if (m > 12) { m = 1; r += 1 }
    setMiesiac(m)
    setRok(r)
  }

  const pracownicy = dane?.pracownicy || []
  const sumaGodzin = useMemo(() => pracownicy.reduce((a, p) => a + (p.suma_godzin || 0), 0), [pracownicy])
  const naPrzyszlosc = rok > dzis.getFullYear() || (rok === dzis.getFullYear() && miesiac >= dzis.getMonth() + 1)

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Godziny kuchni</h2>
          <p className="mt-1 text-sm text-muted">Przepracowane godziny pracowników kuchni (RCP). Bez kwot.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => przesunMiesiac(-1)}
            className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-95"
            aria-label="Poprzedni miesiąc"
          >
            <Icon name="chevronDown" className="h-4 w-4 rotate-90" />
          </button>
          <span className="min-w-[150px] text-center font-display text-base font-bold capitalize text-ink">{etykietaMiesiaca}</span>
          <button
            onClick={() => przesunMiesiac(1)}
            disabled={naPrzyszlosc}
            className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-95 disabled:opacity-30"
            aria-label="Następny miesiąc"
          >
            <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <>
          {/* Kto teraz na zmianie (live, kuchnia) — odświeża się co 20 s */}
          {dane?.na_zmianie?.length > 0 && (
            <div className="mb-6 rounded-xl border border-mint/30 bg-mint/[0.05] p-4">
              <div className="mb-3 flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-mint" />
                </span>
                <span className="text-sm font-bold text-ink">Na zmianie teraz ({dane.na_zmianie.length})</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {dane.na_zmianie.map((z, i) => (
                  <span key={i} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white/[0.03] px-2.5 py-1 text-xs">
                    <span className="font-semibold text-ink">{z.pracownik}</span>
                    <span className="font-mono text-muted">od {z.wejscie.slice(11, 16)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Podsumowanie (bez kwot) */}
          <div className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-2 rounded-xl border border-line bg-white/[0.02] px-5 py-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Łącznie (kuchnia)</div>
              <div className="font-display text-2xl font-bold text-gradient tabular-nums">{godzinyHM(sumaGodzin)}</div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Pracownicy z godzinami</div>
              <div className="font-display text-2xl font-bold text-ink tabular-nums">{pracownicy.length}</div>
            </div>
          </div>

          {pracownicy.length === 0 ? (
            <Card className="p-8 text-center text-sm text-muted">
              Brak zarejestrowanych godzin kuchni w tym miesiącu.
            </Card>
          ) : (
            <div className="space-y-3">
              {pracownicy.map((p) => {
                const maxG = Math.max(1, ...p.stanowiska.map((s) => s.godziny))
                return (
                  <div key={p.pracownik_id} className="rounded-xl border border-line bg-white/[0.02] p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <span className="min-w-0 truncate font-semibold text-ink">{p.pracownik}</span>
                      <span className="font-display font-bold tabular-nums text-ink">{godzinyHM(p.suma_godzin)}</span>
                    </div>
                    <div className="space-y-2">
                      {p.stanowiska.map((s) => (
                        <div key={s.stanowisko} className="flex items-center gap-3">
                          <span className="w-28 shrink-0 truncate text-xs text-muted" title={s.stanowisko}>{s.stanowisko}</span>
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                            <div className="h-full rounded-full bg-accent-gradient" style={{ width: `${(s.godziny / maxG) * 100}%` }} />
                          </div>
                          <span className="w-12 shrink-0 text-right font-mono text-xs font-bold text-ink tabular-nums">{godzinyHM(s.godziny)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}
    </Card>
  )
}

// Panel „Szef kuchni" — oversight tylko do odczytu: godziny kuchni (bez wypłat),
// podgląd stołów na żywo, rezerwacje. Bez grafiku i bez żadnej edycji.
export default function SzefKuchniView() {
  const { user, logout } = useAuth()
  const [widok, setWidok] = useState('kuchnia')
  const imie = user?.imie || user?.login

  return (
    <div className="relative min-h-dvh bg-bg">
      <div aria-hidden className="pointer-events-none absolute -right-40 -top-40 h-96 w-96 rounded-full bg-page-glow opacity-[0.07] blur-2xl transform-gpu" />

      <header className="relative z-10 flex items-center justify-between border-b border-line bg-bg-2/60 px-safe pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur">
        <div className="flex items-center gap-3">
          <Logo className="h-8" variant="gradient" />
          <div>
            <h1 className="font-display text-base font-bold text-ink md:text-lg">Rajcula</h1>
            <p className="text-xs text-muted">Panel szefa kuchni{imie ? ` · ${imie}` : ''}</p>
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
        {/* Przewijany pasek zakładek */}
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
          {widok === 'kuchnia' && <KuchniaGodziny />}
          {widok === 'stoly' && <StolyLive />}
          {widok === 'rezerwacje' && <Rezerwacje />}
        </div>
      </main>
    </div>
  )
}
