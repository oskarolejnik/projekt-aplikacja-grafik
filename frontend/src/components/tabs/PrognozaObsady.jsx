import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Prognoza obsady — sugerowana liczba osób na zmianę wg prognozowanego ruchu.
// Czysta agregacja z /api/prognoza-ruchu (zero zapisu). Parametry ustawia się w „Ustawienia lokalu”.
export default function PrognozaObsady() {
  const { toast } = useToast()
  const [dni, setDni] = useState(90)
  const [d, setD] = useState(null)
  const [loading, setLoading] = useState(true)

  const [stanowiska, setStanowiska] = useState([])
  const [stanId, setStanId] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setD(await api(`/prognoza-ruchu?dni=${dni}`)) }
    catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [dni, toast])
  useEffect(() => { load() }, [load])

  // Lista stanowisk do wyboru celu auto-obsady (domyślnie pierwsze stanowisko Sali).
  useEffect(() => {
    api('/stanowiska').then((lista) => {
      const arr = Array.isArray(lista) ? lista : []
      setStanowiska(arr)
      const sala = arr.find((s) => (s.nazwa || '').toLowerCase().startsWith('sala')) || arr[0]
      if (sala) setStanId(String(sala.id))
    }).catch(() => {})
  }, [])

  const zastosuj = async () => {
    if (!stanId) { toast('Wybierz stanowisko.', 'error'); return }
    setBusy(true)
    try {
      const r = await api('/wymagania/z-prognozy', 'POST', { stanowisko_id: Number(stanId) })
      toast(`Zastosowano obsadę na ${r.zastosowano} dni (${r.stanowisko}).`, 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const maxProg = d ? Math.max(1, ...d.projekcja_7dni.map((p) => p.prognoza)) : 1

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Prognoza obsady" subtitle="Sugerowana liczba osób na zmianę wg prognozowanego ruchu (7 dni)." />
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted">Okno historii:</span>
          <select value={dni} onChange={(e) => setDni(Number(e.target.value))}
                  className="rounded-lg border border-line bg-surface px-3 py-1.5 text-ink outline-none focus:border-mint">
            <option value={30}>30 dni</option>
            <option value={90}>90 dni</option>
            <option value={180}>180 dni</option>
            <option value={365}>365 dni</option>
          </select>
        </div>
      </div>

      {loading || !d ? (
        <div className="grid place-items-center py-20"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-line bg-surface-2 p-5">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
                <Icon name="pin" className="h-4 w-4" /> Średni ruch
              </div>
              <div className="font-display text-2xl font-bold text-ink">{d.srednia_dzienna}</div>
              <div className="mt-1 text-xs text-muted">rachunków/dzień · {d.probek} próbek</div>
            </div>
            <div className="rounded-2xl border border-line bg-surface-2 p-5">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
                <Icon name="clock" className="h-4 w-4" /> Trend (28 dni)
              </div>
              <div className={`font-display text-2xl font-bold ${d.trend_28d_proc == null ? 'text-muted' : d.trend_28d_proc >= 0 ? 'text-mint' : 'text-danger'}`}>
                {d.trend_28d_proc == null ? '—' : `${d.trend_28d_proc > 0 ? '+' : ''}${d.trend_28d_proc}%`}
              </div>
              <div className="mt-1 text-xs text-muted">zmiana ruchu tydzień do tygodnia</div>
            </div>
            <div className="rounded-2xl border border-line bg-surface-2 p-5">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
                <Icon name="users" className="h-4 w-4" /> Parametry
              </div>
              <div className="font-display text-2xl font-bold text-ink">{d.parametry_obsady.rachunki_na_osobe}</div>
              <div className="mt-1 text-xs text-muted">rachunków/osobę · min. {d.parametry_obsady.min} os.</div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="py-2 pr-3 font-semibold">Dzień</th>
                  <th className="py-2 pr-3 font-semibold">Data</th>
                  <th className="py-2 pr-3 text-right font-semibold">Prognoza ruchu</th>
                  <th className="py-2 pr-3 font-semibold">Obciążenie</th>
                  <th className="py-2 pr-3 text-right font-semibold">Sugerowana obsada</th>
                </tr>
              </thead>
              <tbody>
                {d.projekcja_7dni.map((p) => (
                  <tr key={p.data} className="border-b border-line/60">
                    <td className="py-2.5 pr-3 font-semibold text-ink">{p.nazwa}</td>
                    <td className="py-2.5 pr-3 text-muted">{p.data}</td>
                    <td className="py-2.5 pr-3 text-right text-ink">{p.prognoza}</td>
                    <td className="py-2.5 pr-3">
                      <div className="h-2 w-full min-w-[80px] rounded-full bg-surface">
                        <div className="h-2 rounded-full bg-accent-gradient" style={{ width: `${Math.round((p.prognoza / maxProg) * 100)}%` }} />
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 text-right">
                      <span className="rounded-full bg-mint/15 px-2.5 py-1 font-display font-bold text-mint">{p.sugerowana_obsada}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Auto-obsada: zamień prognozę w wymagania grafiku jednym klikiem. */}
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-mint/30 bg-mint/[0.05] p-4">
            <div className="min-w-[200px] flex-1">
              <div className="text-sm font-semibold text-ink">Zastosuj sugerowaną obsadę do grafiku</div>
              <div className="text-xs text-muted">Utworzy wymagania na 7 dni dla wybranego stanowiska (istniejące na ten dzień nadpisze).</div>
            </div>
            <select value={stanId} onChange={(e) => setStanId(e.target.value)}
                    className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-mint">
              {stanowiska.map((s) => <option key={s.id} value={s.id}>{s.nazwa}</option>)}
            </select>
            <button onClick={zastosuj} disabled={busy || !stanId}
                    className="rounded-xl bg-accent-gradient px-4 py-2 text-sm font-bold text-bg shadow-cta transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60">
              {busy ? 'Stosuję…' : 'Zastosuj do wymagań'}
            </button>
          </div>

          <div className="rounded-xl border border-line bg-surface-2 px-4 py-3 text-xs text-muted">
            Sugerowaną obsadę liczymy jako <b className="text-ink">max(min, ⌈prognoza ÷ rachunki_na_osobę⌉)</b>.
            Parametry zmienisz w zakładce <b className="text-ink">Ustawienia lokalu</b>.
          </div>
        </div>
      )}
    </Card>
  )
}
