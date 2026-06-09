import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from '../components/ui/Toast'
import { godzinyHM, NAZWY_DNI, ddmmyyyy, zl } from '../lib/format'

// Zakładka „Godziny": miesięczne podsumowanie przepracowanych godzin pracownika
// — suma u góry (HH:MM), podział na dni i na stanowiska (dane z RCP × opublikowany grafik).
export default function EmployeeHours() {
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
      setDane(await api(`/me/godziny?rok=${rok}&miesiac=${miesiac}`))
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

  const stanowiska = dane?.stanowiska || []
  const dni = dane?.dni || []
  const maxGodziny = Math.max(1, ...stanowiska.map((s) => s.godziny))
  const naPrzyszlosc = rok > dzis.getFullYear() || (rok === dzis.getFullYear() && miesiac >= dzis.getMonth() + 1)

  return (
    <div className="space-y-6">
      {/* Nawigacja miesiącem */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => przesunMiesiac(-1)}
          className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-95"
          aria-label="Poprzedni miesiąc"
        >
          <Icon name="chevronDown" className="h-4 w-4 rotate-90" />
        </button>
        <span className="font-display text-lg font-bold capitalize text-ink">{etykietaMiesiaca}</span>
        <button
          onClick={() => przesunMiesiac(1)}
          disabled={naPrzyszlosc}
          className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-95 disabled:opacity-30"
          aria-label="Następny miesiąc"
        >
          <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
        </button>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <>
          {/* Trwająca, niezakończona zmiana — „dziś jesteś na zmianie" (pulsująca kropka). */}
          {dane?.aktywna_zmiana && (
            <Card className="flex items-center gap-3 border-mint/30 bg-mint/[0.06] p-4">
              <span className="relative flex h-3 w-3 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
                <span className="relative inline-flex h-3 w-3 rounded-full bg-mint" />
              </span>
              <div className="min-w-0">
                <div className="text-sm font-bold text-ink">Zmiana w toku — dziś</div>
                <div className="text-xs text-muted">
                  Rozpoczęta o {dane.aktywna_zmiana.wejscie.slice(11, 16)} — godziny doliczą się po wybiciu wyjścia.
                </div>
              </div>
            </Card>
          )}

          {/* Suma godzin + do wypłaty (u góry) */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Card className="p-6 text-center">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted">Łącznie w miesiącu</div>
              <div className="mt-1 font-display text-4xl font-bold text-gradient tabular-nums sm:text-5xl">
                {godzinyHM(dane?.suma_godzin)}
              </div>
            </Card>
            <Card className="border-mint/30 bg-mint/[0.05] p-6 text-center">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted">Do wypłaty</div>
              <div className="mt-1 font-display text-4xl font-bold tabular-nums text-mint sm:text-5xl">
                {zl(dane?.do_wyplaty)}
              </div>
            </Card>
          </div>

          {(dane?.suma_godzin ?? 0) === 0 ? (
            <Card className="p-8 text-center text-sm text-muted">
              Brak zarejestrowanych godzin w tym miesiącu. Godziny pojawią się po odbiciach RCP.
            </Card>
          ) : (
            <>
              {/* Podział na dni — w jakim dniu ile przepracowano */}
              {dni.length > 0 && (
                <Card className="p-4 sm:p-5">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Według dni</div>
                  <div className="space-y-0.5">
                    {dni.map((d) => (
                      <div key={d.data} className="flex items-center justify-between border-b border-line/60 py-2 last:border-0">
                        <div className="flex items-baseline gap-2">
                          <span className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(d.data).getDay()]}</span>
                          <span className="text-xs text-muted">{ddmmyyyy(d.data)}</span>
                        </div>
                        <span className="font-mono font-bold tabular-nums text-ink">{godzinyHM(d.godziny)}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Rozbicie na stanowiska */}
              {stanowiska.length > 0 && (
                <div className="space-y-3">
                  <div className="px-1 text-xs font-semibold uppercase tracking-wider text-muted">Według stanowisk</div>
                  {stanowiska.map((s) => (
                    <Card key={s.stanowisko} className="p-4">
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <span className="font-semibold text-ink">{s.stanowisko}</span>
                          {s.stawka > 0 && <span className="ml-2 text-xs text-muted">{zl(s.stawka)}/h</span>}
                        </div>
                        <div className="shrink-0 text-right">
                          <div className="font-display font-bold tabular-nums text-ink">{godzinyHM(s.godziny)}</div>
                          {s.kwota > 0 && <div className="text-xs font-semibold tabular-nums text-mint">{zl(s.kwota)}</div>}
                        </div>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                        <div
                          className="h-full rounded-full bg-accent-gradient transition-[width] duration-500"
                          style={{ width: `${(s.godziny / maxGodziny) * 100}%` }}
                        />
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
