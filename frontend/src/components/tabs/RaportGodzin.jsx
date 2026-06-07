import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Raport godzin (admin): miesięczne podsumowanie przepracowanych godzin wszystkich
// pracowników z rozbiciem na stanowiska (RCP × opublikowany grafik). Tylko odczyt.
// Dane: GET /api/raporty/godziny?rok=&miesiac= (raporty.raport_godzin_miesiac).
export default function RaportGodzin() {
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
      setDane(await api(`/raporty/godziny?rok=${rok}&miesiac=${miesiac}`))
    } catch (e) {
      if (!silent) {
        toast(e.message, 'error')
        setDane(null)
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [rok, miesiac, toast])

  useEffect(() => {
    load()
  }, [load])

  // Live: ciche odświeżanie co 20 s (bez spinnera), tylko gdy karta jest widoczna.
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, 20000)
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
  const niedopasowani = dane?.niedopasowani_rcp || []
  const sumaWszystkich = useMemo(() => pracownicy.reduce((acc, p) => acc + (p.suma_godzin || 0), 0), [pracownicy])
  const naPrzyszlosc = rok > dzis.getFullYear() || (rok === dzis.getFullYear() && miesiac >= dzis.getMonth() + 1)

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Raport godzin</h2>
          <p className="mt-1 text-sm text-muted">Przepracowane godziny (RCP) z podziałem na stanowiska z opublikowanego grafiku.</p>
        </div>
        {/* Nawigacja miesiącem */}
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
          {/* Na zmianie TERAZ (live) — niezakończone odbicia. Odświeża się co 20 s. */}
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
                    {!z.dopasowany && <span className="rounded bg-lemon/15 px-1 text-[10px] font-bold text-lemon">niedopasowany</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Pasek podsumowania zbiorczego */}
          <div className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-2 rounded-xl border border-line bg-white/[0.02] px-5 py-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Łącznie (wszyscy)</div>
              <div className="font-display text-2xl font-bold text-gradient tabular-nums">
                {sumaWszystkich.toFixed(1)}<span className="ml-1 text-base text-muted">h</span>
              </div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Pracownicy z godzinami</div>
              <div className="font-display text-2xl font-bold text-ink tabular-nums">{pracownicy.length}</div>
            </div>
          </div>

          {pracownicy.length === 0 ? (
            <Card className="p-8 text-center text-sm text-muted">
              Brak zarejestrowanych godzin w tym miesiącu. Godziny pojawią się po odbiciach RCP
              i opublikowaniu grafiku.
            </Card>
          ) : (
            <div className="space-y-3">
              {pracownicy.map((p) => {
                const maxG = Math.max(1, ...p.stanowiska.map((s) => s.godziny))
                return (
                  <div key={p.pracownik_id} className="rounded-xl border border-line bg-white/[0.02] p-4">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <span className="font-semibold text-ink">{p.pracownik}</span>
                      <span className="shrink-0 font-display font-bold tabular-nums text-ink">{p.suma_godzin.toFixed(1)} h</span>
                    </div>
                    <div className="space-y-2">
                      {p.stanowiska.map((s) => (
                        <div key={s.stanowisko} className="flex items-center gap-3">
                          <span className="w-40 shrink-0 truncate text-xs text-muted" title={s.stanowisko}>{s.stanowisko}</span>
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                            <div className="h-full rounded-full bg-accent-gradient" style={{ width: `${(s.godziny / maxG) * 100}%` }} />
                          </div>
                          <span className="w-14 shrink-0 text-right font-mono text-xs font-bold text-ink tabular-nums">{s.godziny.toFixed(1)}h</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Odbicia RCP, których nie dopasowano do konta pracownika */}
          {niedopasowani.length > 0 && (
            <Banner variant="warn" className="mt-6">
              <div className="font-semibold">Niedopasowane odbicia RCP ({niedopasowani.length})</div>
              <p className="mt-1 text-xs">
                Te godziny nie zostały przypisane do żadnego konta pracownika (brak powiązania imię/nazwisko ↔ konto):
              </p>
              <ul className="mt-2 space-y-0.5 text-xs">
                {niedopasowani.map((n) => (
                  <li key={n.imie_nazwisko} className="flex justify-between gap-3">
                    <span>{n.imie_nazwisko || '(brak nazwiska)'}</span>
                    <span className="font-mono font-bold tabular-nums">{n.godziny.toFixed(1)} h</span>
                  </li>
                ))}
              </ul>
            </Banner>
          )}
        </>
      )}
    </Card>
  )
}
