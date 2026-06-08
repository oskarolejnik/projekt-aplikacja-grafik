import { useEffect, useState, useCallback } from 'react'
import { Card } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, NAZWY_DNI } from '../../lib/format'

// Live podgląd zajętości stołów z Gastro (snapshot wypychany przez agenta) + historia 30 dni.
function Tile({ label, value, accent }) {
  return (
    <div className={`rounded-xl border p-4 text-center ${accent ? 'border-blush/30 bg-blush/[0.06]' : 'border-line bg-white/[0.02]'}`}>
      <div className="font-display text-3xl font-bold tabular-nums text-ink">{value ?? 0}</div>
      <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-muted">{label}</div>
    </div>
  )
}

// Historia: dzienne słupki liczby obsłużonych stolików (najnowsze u góry) + suma/średnia.
function HistoriaView({ dni }) {
  if (!dni || dni.length === 0) {
    return <Banner variant="warn">Brak danych historycznych — agent jeszcze nie przysłał historii stołów.</Banner>
  }
  const maxL = Math.max(1, ...dni.map((d) => d.liczba))
  const total = dni.reduce((a, d) => a + d.liczba, 0)
  const srednia = dni.length ? Math.round(total / dni.length) : 0
  const lista = [...dni].reverse() // najnowsze u góry
  return (
    <>
      <div className="mb-4 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="text-muted">Suma: <b className="tabular-nums text-ink">{total}</b></span>
        <span className="text-muted">Średnio: <b className="tabular-nums text-ink">{srednia}</b>/dzień</span>
        <span className="text-muted">Dni: <b className="tabular-nums text-ink">{dni.length}</b></span>
      </div>
      <div className="space-y-1.5">
        {lista.map((d) => {
          const dt = new Date(d.data)
          const isW = [0, 6].includes(dt.getDay())
          return (
            <div key={d.data} className="flex items-center gap-3 text-sm">
              <div className="w-24 shrink-0">
                <div className={`font-semibold capitalize leading-tight ${isW ? 'text-blush' : 'text-ink'}`}>{NAZWY_DNI[dt.getDay()]}</div>
                <div className="text-xs text-muted">{ddmmyyyy(d.data)}</div>
              </div>
              <div className="h-3 flex-1 overflow-hidden rounded-full bg-white/[0.04]">
                <div className="h-full rounded-full bg-accent-gradient transition-all" style={{ width: `${Math.max(3, Math.round((d.liczba / maxL) * 100))}%` }} />
              </div>
              <span className="w-9 shrink-0 text-right font-mono font-bold tabular-nums text-ink">{d.liczba}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

export default function StolyLive() {
  const { toast } = useToast()
  const [tryb, setTryb] = useState('live') // 'live' | 'historia'
  const [dane, setDane] = useState(null)
  const [historia, setHistoria] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadLive = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setDane(await api('/gastro/stoly'))
    } catch (e) {
      if (!silent) toast(e.message, 'error')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [toast])

  const loadHistoria = useCallback(async () => {
    setLoading(true)
    try {
      setHistoria((await api('/gastro/stoly-historia')).dni || [])
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    if (tryb === 'live') loadLive()
    else loadHistoria()
  }, [tryb, loadLive, loadHistoria])

  // Live: ciche odświeżanie co 15 s (tylko w trybie live i gdy karta widoczna).
  useEffect(() => {
    if (tryb !== 'live') return undefined
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') loadLive(true)
    }, 15000)
    return () => clearInterval(id)
  }, [tryb, loadLive])

  const wewnatrz = dane?.wewnatrz || []
  const razem = (dane?.wewnatrz_suma || 0) + (dane?.na_zewnatrz || 0)
  const brakDanych = !loading && !dane?.zaktualizowano_at

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-xl border border-line bg-white/[0.03] p-1">
          {[['live', 'Na żywo'], ['historia', 'Historia (30 dni)']].map(([v, l]) => (
            <button
              key={v}
              onClick={() => setTryb(v)}
              className={`rounded-lg px-3 py-1.5 text-sm font-bold transition active:scale-[0.97] ${tryb === v ? 'bg-accent-gradient text-bg shadow-glow' : 'text-muted hover:text-ink'}`}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              {l}
            </button>
          ))}
        </div>
        {tryb === 'live' && (
          <div className="ml-auto flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-mint" />
            </span>
            <span className="text-sm font-semibold text-muted">zajęte teraz</span>
            <span className="font-display text-3xl font-bold text-gradient tabular-nums">{razem}</span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : tryb === 'historia' ? (
        <HistoriaView dni={historia} />
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

          {/* Kuchnia — DANIA do wydania (niewydane pozycje kierunku Kuchnia na realnych rewirach, bez R2Piw). */}
          <div className="mt-3 rounded-xl border border-lemon/30 bg-lemon/[0.06] p-4 text-center">
            <div className="font-display text-3xl font-bold tabular-nums text-ink">{dane?.kuchnia ?? 0}</div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">Kuchnia — dania do wydania</div>
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
