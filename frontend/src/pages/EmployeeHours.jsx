import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from '../components/ui/Toast'

// Zakładka „Godziny": miesięczne podsumowanie przepracowanych godzin pracownika
// z podziałem na stanowiska (dane z RCP × opublikowany grafik). Tylko odczyt.
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

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setDane(await api(`/me/godziny?rok=${rok}&miesiac=${miesiac}`))
    } catch (e) {
      toast(e.message, 'error')
      setDane(null)
    } finally {
      setLoading(false)
    }
  }, [rok, miesiac, toast])

  useEffect(() => {
    load()
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

          {/* Suma godzin */}
          <Card className="p-6 text-center">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">Łącznie w miesiącu</div>
            <div className="mt-1 font-display text-5xl font-bold text-gradient tabular-nums">
              {(dane?.suma_godzin ?? 0).toFixed(1)}
              <span className="ml-1 text-2xl text-muted">h</span>
            </div>
          </Card>

          {/* Rozbicie na stanowiska */}
          {stanowiska.length === 0 ? (
            <Card className="p-8 text-center text-sm text-muted">
              Brak zarejestrowanych godzin w tym miesiącu. Godziny pojawią się po odbiciach RCP
              i opublikowaniu grafiku.
            </Card>
          ) : (
            <div className="space-y-3">
              {stanowiska.map((s) => (
                <Card key={s.stanowisko} className="p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="font-semibold text-ink">{s.stanowisko}</span>
                    <span className="font-display font-bold tabular-nums text-ink">{s.godziny.toFixed(1)} h</span>
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
    </div>
  )
}
