import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { WeekSelect } from '../ui/WeekSelect'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, NAZWY_DNI } from '../../lib/format'

// Grafik sprzątania — widok ADMINA. Pozycje generowane z reguł (Parter/Góra codziennie,
// Zielona w niedziele, pozostałe sale dzień po imprezie: R2P→Zielona, R2Piw→Lustrzana,
// R2G→Kryształowa). Admin może usunąć wygenerowaną pozycję albo dodać własną
// (przesunięcie = usuń na starym dniu + dodaj na nowym). ✓ pokazuje odhaczenia sprzątaczki.
export default function Sprzatanie() {
  const { week } = useData()
  const { toast } = useToast()
  const [dane, setDane] = useState({ pozycje: [], sale: [] })
  const [loading, setLoading] = useState(true)
  const [wybor, setWybor] = useState({}) // data -> sala wybrana w selektorze „dodaj"
  const [s, e] = week.split('|')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setDane(await api(`/sprzatanie?start=${s}&end=${e}`))
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [s, e, toast])

  useEffect(() => { load() }, [load])

  const korekta = async (data, sala, akcja) => {
    try {
      await api('/sprzatanie/korekty', 'POST', { data, sala, akcja })
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const dni = {}
  dane.pozycje.forEach((p) => { (dni[p.data] = dni[p.data] || []).push(p) })

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <WeekSelect />
      </div>
      <SectionHeader
        title="Grafik sprzątania sal"
        subtitle="Generowany automatycznie: Parter i Góra codziennie, Zielona w niedziele, pozostałe sale dzień po imprezie. Przesunięcie = usuń pozycję i dodaj ją na innym dniu."
      />
      {loading ? (
        <div className="grid place-items-center py-12">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Object.keys(dni).sort().map((d) => {
            const zajete = new Set(dni[d].map((p) => p.sala))
            const dostepne = (dane.sale || []).filter((x) => !zajete.has(x))
            return (
              <div key={d} className="rounded-2xl border border-line bg-white/[0.02] p-4">
                <div className="mb-3 flex items-baseline gap-2">
                  <span className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(d).getDay()]}</span>
                  <span className="text-xs text-muted">{ddmmyyyy(d)}</span>
                </div>
                <div className="space-y-2">
                  {dni[d].map((p) => (
                    <div key={p.sala} className={`flex items-center justify-between gap-2 rounded-xl border p-2.5 ${p.zrobione ? 'border-success/40 bg-success/10' : 'border-line bg-surface-2'}`}>
                      <div className="min-w-0">
                        <div className={`flex items-center gap-1.5 text-sm font-bold ${p.zrobione ? 'text-success' : 'text-ink'}`}>
                          {p.zrobione && <Icon name="check" className="h-3.5 w-3.5" strokeWidth={3} />}
                          {p.sala}
                        </div>
                        <div className="truncate text-[11px] text-muted">
                          {p.powody.join(' · ')}
                          {p.zrobione_przez ? ` · ✓ ${p.zrobione_przez}` : ''}
                        </div>
                      </div>
                      <button
                        onClick={() => korekta(d, p.sala, 'usun')}
                        className="rounded-lg border border-danger/20 bg-danger/10 p-1.5 text-danger transition hover:bg-danger/20"
                        aria-label={`Usuń ${p.sala}`}
                        title="Usuń pozycję"
                      >
                        <Icon name="trash" className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                  {dostepne.length > 0 && (
                    <div className="flex gap-1.5 pt-1">
                      <select
                        value={wybor[d] || ''}
                        onChange={(ev) => setWybor((w) => ({ ...w, [d]: ev.target.value }))}
                        className="field min-w-0 flex-1 px-2 py-1.5 text-xs"
                      >
                        <option value="" className="bg-surface">+ dodaj salę…</option>
                        {dostepne.map((x) => (
                          <option key={x} value={x} className="bg-surface text-ink">{x}</option>
                        ))}
                      </select>
                      <button
                        onClick={() => wybor[d] && korekta(d, wybor[d], 'dodaj')}
                        disabled={!wybor[d]}
                        className="rounded-lg border border-line bg-white/[0.04] px-2.5 text-sm font-semibold text-mint transition hover:bg-white/[0.08] disabled:opacity-40"
                        aria-label="Dodaj salę"
                      >
                        <Icon name="plus" className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
