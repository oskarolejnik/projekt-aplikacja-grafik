import { useEffect, useState, useCallback } from 'react'
import { Card } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Live podgląd zajętości stołów z Gastro (snapshot wypychany przez agenta).
// Wewnątrz (sale osobno) → na zewnątrz (suma) → na wynos. Odświeża się co 15 s.
function Tile({ label, value, accent }) {
  return (
    <div className={`rounded-xl border p-4 text-center ${accent ? 'border-blush/30 bg-blush/[0.06]' : 'border-line bg-white/[0.02]'}`}>
      <div className="font-display text-3xl font-bold tabular-nums text-ink">{value ?? 0}</div>
      <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-muted">{label}</div>
    </div>
  )
}

export default function StolyLive() {
  const { toast } = useToast()
  const [dane, setDane] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setDane(await api('/gastro/stoly'))
    } catch (e) {
      if (!silent) toast(e.message, 'error')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  // Live: ciche odświeżanie co 15 s (tylko gdy karta widoczna).
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, 15000)
    return () => clearInterval(id)
  }, [load])

  const wewnatrz = dane?.wewnatrz || []
  const razem = (dane?.wewnatrz_suma || 0) + (dane?.na_zewnatrz || 0)
  const brakDanych = !loading && !dane?.zaktualizowano_at

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-5 flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-mint" />
        </span>
        <h2 className="font-display text-xl font-bold text-ink sm:text-2xl">Stoły zajęte teraz</h2>
        <span className="ml-auto font-display text-3xl font-bold text-gradient tabular-nums">{razem}</span>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : brakDanych ? (
        <Banner variant="warn">Brak danych o stołach — agent jeszcze nic nie przysłał (sprawdź, czy działa).</Banner>
      ) : (
        <>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Wewnątrz</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {wewnatrz.map((w) => (
              <Tile key={w.nazwa} label={w.nazwa} value={w.liczba} />
            ))}
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <Tile label="Na zewnątrz" value={dane?.na_zewnatrz} accent />
            <Tile label="Na wynos" value={dane?.wynos} accent />
          </div>

          {dane?.zaktualizowano_at && (
            <div className="mt-4 text-right text-xs text-muted">
              Aktualizacja: {new Date(dane.zaktualizowano_at).toLocaleTimeString('pl-PL')}
            </div>
          )}
        </>
      )}
    </Card>
  )
}
