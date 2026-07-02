import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Giełda wymiany zmian — widok managera. Akceptacja przepina przydział na przejmującego.
const STATUS_L = {
  otwarta: 'Otwarta', zajeta: 'Czeka na decyzję', zaakceptowana: 'Zaakceptowana', anulowana: 'Anulowana',
}
const STATUS_KLASA = {
  otwarta: 'bg-white/10 text-muted', zajeta: 'bg-amber-400/15 text-amber-300',
  zaakceptowana: 'bg-mint/15 text-mint', anulowana: 'bg-white/10 text-muted',
}
const FILTRY = [['', 'Wszystkie'], ['zajeta', 'Do decyzji'], ['otwarta', 'Otwarte'], ['zaakceptowana', 'Zaakceptowane']]

export default function GieldaZmian() {
  const { toast } = useToast()
  const [filtr, setFiltr] = useState('')
  const [oferty, setOferty] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setOferty(await api(`/gielda/oferty${filtr ? `?status_filtr=${filtr}` : ''}`)) }
    catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [filtr, toast])
  useEffect(() => { load() }, [load])

  const decyzja = async (id, akcja, komunikat) => {
    setBusy(true)
    try { await api(`/gielda/oferty/${id}/${akcja}`, 'POST'); toast(komunikat, 'success'); await load() }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Giełda zmian" subtitle="Wymiana zmian między pracownikami — akceptacja przepina zmianę na przejmującego." />
        <div className="flex flex-wrap items-center gap-1.5">
          {FILTRY.map(([v, l]) => (
            <button key={v} onClick={() => setFiltr(v)}
                    className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${filtr === v ? 'bg-mint text-bg' : 'border border-line text-muted hover:text-ink'}`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {loading || !oferty ? (
        <div className="grid place-items-center py-20"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : oferty.length === 0 ? (
        <div className="rounded-xl border border-line bg-surface-2 p-8 text-center text-sm text-muted">
          Brak ofert w tym widoku.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-3 font-semibold">Zmiana</th>
                <th className="py-2 pr-3 font-semibold">Stanowisko</th>
                <th className="py-2 pr-3 font-semibold">Oddaje</th>
                <th className="py-2 pr-3 font-semibold">Przejmuje</th>
                <th className="py-2 pr-3 font-semibold">Status</th>
                <th className="py-2 pr-3 text-right font-semibold">Decyzja</th>
              </tr>
            </thead>
            <tbody>
              {oferty.map((o) => (
                <tr key={o.id} className="border-b border-line/60">
                  <td className="py-2.5 pr-3">
                    <span className="font-semibold text-ink">{o.data}</span>{o.godz_od ? <span className="text-muted"> · {o.godz_od}</span> : ''}
                    {o.powod && <div className="text-xs text-muted">„{o.powod}”</div>}
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{o.stanowisko}{o.rewir ? ` · ${o.rewir}` : ''}</td>
                  <td className="py-2.5 pr-3 text-ink">{o.wystawiajacy || '—'}</td>
                  <td className="py-2.5 pr-3 text-ink">{o.przejmujacy || '—'}</td>
                  <td className="py-2.5 pr-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_KLASA[o.status] || ''}`}>{STATUS_L[o.status] || o.status}</span>
                  </td>
                  <td className="py-2.5 pr-3 text-right">
                    {o.status === 'zajeta' ? (
                      <div className="flex justify-end gap-2">
                        <button onClick={() => decyzja(o.id, 'akceptuj', 'Zmiana przepięta na przejmującego.')} disabled={busy}
                                className="rounded-lg bg-mint/20 px-3 py-1.5 text-xs font-semibold text-mint transition hover:bg-mint/30 disabled:opacity-50">
                          Akceptuj
                        </button>
                        <button onClick={() => decyzja(o.id, 'odrzuc', 'Przejęcie odrzucone — oferta wróciła na giełdę.')} disabled={busy}
                                className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-danger disabled:opacity-50">
                          Odrzuć
                        </button>
                      </div>
                    ) : <span className="text-xs text-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
