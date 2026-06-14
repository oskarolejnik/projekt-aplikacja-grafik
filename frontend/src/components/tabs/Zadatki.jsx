import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Zadatki (KP z Gastro) — skrzynka „do przypisania" + przypisane do terminów. Auto-dopasowanie
// po nazwisku+dacie (z opisu); resztę admin przypisuje ręcznie wybierając termin.
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const dz = (s) => { if (!s) return '—'; const [y, m, d] = s.split('-'); return `${d}.${m}.${y}` }

export default function Zadatki() {
  const { toast } = useToast()
  const [dane, setDane] = useState({ przypisane: [], do_przypisania: [] })
  const [terminy, setTerminy] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [z, t] = await Promise.all([api('/zadatki'), api('/terminy?start=2024-01-01&end=2031-12-31')])
      setDane(z); setTerminy(t.terminy || [])
    } catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [toast])

  useEffect(() => { load() }, [load])

  const dopasuj = async () => {
    setBusy(true)
    try { const r = await api('/zadatki/dopasuj', 'POST'); toast(`Dopasowano: ${r.dopasowano}.`, 'success'); load() }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const przypisz = async (zid, tid) => {
    if (!tid) return
    try { await api(`/zadatki/${zid}/przypisz?termin_id=${tid}`, 'PUT'); load() }
    catch (e) { toast(e.message, 'error') }
  }
  const odepnij = async (zid) => {
    try { await api(`/zadatki/${zid}/odepnij`, 'PUT'); load() }
    catch (e) { toast(e.message, 'error') }
  }

  const opcjeTerminow = [...terminy].sort((a, b) => a.data.localeCompare(b.data))
    .map((t) => ({ id: t.id, label: `${dz(t.data)} — ${t.nazwisko}${t.typ ? ` (${t.typ})` : ''}` }))

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Zadatki (KP)" subtitle="Zadatki z Gastro — dopasowane do terminów i czekające na przypisanie." />
        <Button onClick={dopasuj} disabled={busy}><Icon name="refresh" className="h-4 w-4" /> Dopasuj automatycznie</Button>
      </div>

      {loading ? (
        <div className="grid place-items-center py-12"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : (
        <div className="space-y-6">
          {/* DO PRZYPISANIA */}
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-bold text-ink">
              <span className="rounded-md bg-lemon/15 px-2 py-0.5 text-lemon">Do przypisania</span>
              <span className="text-muted">{dane.do_przypisania.length}</span>
            </div>
            {dane.do_przypisania.length === 0 ? (
              <p className="rounded-xl border border-line bg-white/[0.02] p-4 text-sm text-muted">Wszystkie zadatki przypisane. 🎉</p>
            ) : (
              <div className="space-y-2">
                {dane.do_przypisania.map((z) => (
                  <div key={z.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-white/[0.02] p-3">
                    <span className="font-mono font-bold text-ink">{zl(z.kwota)}</span>
                    <span className="text-xs text-muted">przyjęto {dz(z.data)}{z.numer ? ` · ${z.numer}` : ''}</span>
                    <span className="min-w-0 flex-1 truncate text-sm text-ink/90" title={z.opis}>{z.opis || '—'}</span>
                    {(z.nazwisko || z.data_imprezy) && (
                      <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-muted">rozpoznano: {z.nazwisko || '?'}{z.data_imprezy ? ` · ${dz(z.data_imprezy)}` : ''}</span>
                    )}
                    <select defaultValue="" onChange={(e) => przypisz(z.id, e.target.value)}
                      className="rounded-md border border-line bg-surface px-2 py-1.5 text-xs text-ink outline-none focus:border-mint">
                      <option value="">→ przypisz do terminu…</option>
                      {opcjeTerminow.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* PRZYPISANE */}
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-bold text-ink">
              <span className="rounded-md bg-mint/15 px-2 py-0.5 text-mint">Przypisane</span>
              <span className="text-muted">{dane.przypisane.length}</span>
            </div>
            {dane.przypisane.length === 0 ? (
              <p className="rounded-xl border border-line bg-white/[0.02] p-4 text-sm text-muted">Brak przypisanych zadatków.</p>
            ) : (
              <div className="space-y-2">
                {dane.przypisane.map((z) => (
                  <div key={z.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-white/[0.02] p-3">
                    <span className="font-mono font-bold text-ink">{zl(z.kwota)}</span>
                    <span className="min-w-0 flex-1 truncate text-sm text-muted" title={z.opis}>{z.opis || '—'}</span>
                    <Icon name="check" className="h-3.5 w-3.5 text-mint" />
                    <span className="text-sm font-semibold text-ink">{z.termin?.nazwisko} · {dz(z.termin?.data)}{z.termin?.typ ? ` (${z.termin.typ})` : ''}</span>
                    <button onClick={() => odepnij(z.id)} className="rounded-md border border-line px-2 py-1 text-xs font-semibold text-muted hover:text-ink">odepnij</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}
