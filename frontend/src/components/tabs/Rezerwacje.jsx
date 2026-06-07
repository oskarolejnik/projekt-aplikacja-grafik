import { useEffect, useState, useCallback } from 'react'
import { Card } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, NAZWY_DNI } from '../../lib/format'

// Rezerwacje (admin + szef): najbliższe 30 dni, per dzień z rozbiciem na godziny.
// Dane z Google Calendar (events.list), odświeżane co 60 s.
export default function Rezerwacje() {
  const { toast } = useToast()
  const [dni, setDni] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setDni((await api('/rezerwacje')).dni || [])
    } catch (e) {
      if (!silent) toast(e.message, 'error')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, 60000)
    return () => clearInterval(id)
  }, [load])

  const sumaRez = dni.reduce((a, d) => a + d.liczba, 0)
  const sumaOsob = dni.reduce((a, d) => a + d.osoby, 0)

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Rezerwacje</h2>
          <p className="mt-1 text-sm text-muted">Najbliższe 30 dni, z podziałem na godziny (na żywo z kalendarza).</p>
        </div>
        <div className="flex gap-6">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Rezerwacje</div>
            <div className="font-display text-2xl font-bold text-gradient tabular-nums">{sumaRez}</div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Osoby</div>
            <div className="font-display text-2xl font-bold text-ink tabular-nums">{sumaOsob}</div>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : dni.length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted">
          Brak rezerwacji na najbliższe 30 dni (albo kalendarz nie jest jeszcze połączony).
        </Card>
      ) : (
        <div className="space-y-3">
          {dni.map((d) => {
            const isW = [0, 6].includes(new Date(d.data).getDay())
            return (
              <div key={d.data} className="rounded-xl border border-line bg-white/[0.02] p-4">
                <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex items-baseline gap-2">
                    <span className={`font-semibold capitalize ${isW ? 'text-blush' : 'text-ink'}`}>{NAZWY_DNI[new Date(d.data).getDay()]}</span>
                    <span className="text-xs text-muted">{ddmmyyyy(d.data)}</span>
                  </div>
                  <span className="text-sm font-bold text-ink">{d.liczba} rez. · {d.osoby} os.</span>
                </div>
                <div className="space-y-1">
                  {d.godziny.map((g) => (
                    <div key={g.godzina} className="flex items-center gap-3 border-b border-line/50 py-1 text-sm last:border-0">
                      <span className="w-16 shrink-0 font-mono font-semibold text-ink">{g.godzina}</span>
                      <span className="text-muted">{g.liczba} rez.</span>
                      <span className="ml-auto font-mono font-bold tabular-nums text-ink">{g.osoby} os.</span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
