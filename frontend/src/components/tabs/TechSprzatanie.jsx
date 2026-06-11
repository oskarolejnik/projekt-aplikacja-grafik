import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { WeekSelect } from '../ui/WeekSelect'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, NAZWY_DNI } from '../../lib/format'

// Grafik sprzątania sal — widok działu technicznego (sprzątaczka).
// Pozycje generuje backend z reguł: Parter/Góra codziennie, Zielona w niedziele,
// pozostałe sale dzień po imprezie. Kliknięcie pozycji = ✓ „zrobione" (i odwrotnie).
export default function TechSprzatanie() {
  const { week, biezacy, setWeek } = useData()
  const { toast } = useToast()
  const [pozycje, setPozycje] = useState([])
  const [loading, setLoading] = useState(true)

  // Sprzątanie dotyczy bieżącego tygodnia — ustaw go na wejściu.
  useEffect(() => { setWeek(biezacy) }, [biezacy, setWeek])
  const [s, e] = week.split('|')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setPozycje((await api(`/me/sprzatanie?start=${s}&end=${e}`)).pozycje || [])
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [s, e, toast])

  useEffect(() => { load() }, [load])

  const odhacz = async (p) => {
    try {
      await api('/me/sprzatanie/zrobione', 'PUT', { data: p.data, sala: p.sala, zrobione: !p.zrobione })
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const dni = {}
  pozycje.forEach((p) => { (dni[p.data] = dni[p.data] || []).push(p) })

  return (
    <Card className="mx-auto max-w-3xl p-6 sm:p-8">
      <div className="mb-5">
        <WeekSelect />
      </div>
      <SectionHeader
        title="Sprzątanie sal"
        subtitle={`Plan na tydzień ${ddmmyyyy(s)} — ${ddmmyyyy(e)}. Kliknij pozycję, gdy sala posprzątana.`}
      />
      {loading ? (
        <div className="grid place-items-center py-12">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <div className="space-y-3">
          {Object.keys(dni).sort().map((d) => (
            <div key={d} className="rounded-2xl border border-line bg-white/[0.02] p-4">
              <div className="mb-3 flex items-baseline gap-2">
                <span className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(d).getDay()]}</span>
                <span className="text-xs text-muted">{ddmmyyyy(d)}</span>
              </div>
              <div className="space-y-2">
                {dni[d].map((p) => (
                  <button
                    key={p.sala}
                    onClick={() => odhacz(p)}
                    className={`flex w-full items-center justify-between gap-3 rounded-xl border p-3 text-left transition active:scale-[0.99] ${
                      p.zrobione ? 'border-success/40 bg-success/10' : 'border-line bg-surface-2 hover:border-mint/40'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className={`font-bold ${p.zrobione ? 'text-success line-through' : 'text-ink'}`}>{p.sala}</div>
                      <div className="truncate text-xs text-muted">
                        {p.powody.join(' · ')}
                        {p.zrobione_przez ? ` · ✓ ${p.zrobione_przez}` : ''}
                      </div>
                    </div>
                    <span
                      className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${
                        p.zrobione ? 'bg-success text-bg' : 'border border-line text-muted/50'
                      }`}
                    >
                      <Icon name="check" className="h-4 w-4" strokeWidth={3} />
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
