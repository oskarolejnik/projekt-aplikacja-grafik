import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { num } from '../../lib/num'
import { useToast } from '../ui/Toast'

// Napiwki — widok MANAGERA: pula napiwków dnia dzielona między obsługę sali wg godzin z RCP
// (albo po równo). Manager wpisuje kwotę + sposób, widzi natychmiastowy podział na osoby.
const dzisISO = () => new Date().toISOString().slice(0, 10)
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'

export default function Napiwki() {
  const { toast } = useToast()
  const [data, setData] = useState(dzisISO())
  const [wynik, setWynik] = useState(null)
  const [loading, setLoading] = useState(true)
  const [kwota, setKwota] = useState('')
  const [sposob, setSposob] = useState('godziny')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const w = await api(`/napiwki?data=${data}`)
      setWynik(w); setKwota(w.kwota ? String(w.kwota) : ''); setSposob(w.sposob || 'godziny')
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [data, toast])
  useEffect(() => { load() }, [load])

  const zapisz = async () => {
    setBusy(true)
    try {
      const w = await api(`/napiwki?data=${data}`, 'PUT', { kwota: num(kwota), sposob })
      setWynik(w); toast('Podział napiwków zapisany.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const podzial = wynik?.podzial || []
  const sumaPodzialu = podzial.reduce((s, x) => s + (x.kwota || 0), 0)

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Napiwki" subtitle="Pula napiwków dnia dzielona między obsługę sali — wg przepracowanych godzin (z RCP) albo po równo." />
        <input type="date" value={data} onChange={(e) => setData(e.target.value)}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-mint" />
      </div>

      {/* Wejście: kwota + sposób */}
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Pula napiwków (zł)</span>
          <input inputMode="decimal" value={kwota} onChange={(e) => setKwota(e.target.value)} placeholder="np. 240,50"
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-ink outline-none focus:border-mint" />
        </label>
        <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5">
          {[['godziny', 'Wg godzin'], ['rowno', 'Po równo']].map(([k, l]) => (
            <button key={k} onClick={() => setSposob(k)}
              className={`rounded-md px-3 py-1.5 text-sm font-semibold transition ${sposob === k ? 'bg-mint text-bg' : 'text-muted hover:text-ink'}`}>{l}</button>
          ))}
        </div>
        <Button onClick={zapisz} disabled={busy}>{busy ? 'Zapisuję…' : 'Zapisz podział'}</Button>
      </div>

      {/* Podział */}
      {loading ? (
        <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : podzial.length === 0 ? (
        <div className="mt-6 rounded-xl border border-line bg-surface-2 p-8 text-center text-sm text-muted">
          Brak obsady sali w grafiku na ten dzień. Dodaj przydziały na Sali, aby podzielić napiwki.
        </div>
      ) : (
        <div className="mt-6 overflow-hidden rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface-2 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2.5 font-semibold">Pracownik</th>
                <th className="px-4 py-2.5 text-right font-semibold">Godziny</th>
                <th className="px-4 py-2.5 text-right font-semibold">Napiwek</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {podzial.map((x) => (
                <tr key={x.pracownik_id} className="text-ink">
                  <td className="px-4 py-2.5 font-medium">{x.pracownik}</td>
                  <td className="px-4 py-2.5 text-right text-muted">{sposob === 'godziny' ? `${x.godziny} h` : '—'}</td>
                  <td className="px-4 py-2.5 text-right font-bold text-mint">{zl(x.kwota)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-surface-2/60 text-sm">
              <tr>
                <td className="px-4 py-2.5 font-semibold text-muted">Razem ({podzial.length} os.{wynik.suma_godzin ? ` · ${wynik.suma_godzin} h` : ''})</td>
                <td />
                <td className="px-4 py-2.5 text-right font-bold text-ink">{zl(sumaPodzialu)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
        <Icon name="info" className="h-3.5 w-3.5" />
        „Wg godzin" dzieli proporcjonalnie do godzin z RCP; przy braku odbić — po równo. Suma zawsze zgadza się co do grosza.
      </p>
    </Card>
  )
}
