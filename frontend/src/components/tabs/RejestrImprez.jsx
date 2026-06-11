import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'

// Rejestr rozliczeń imprez (admin) — OSOBNO od raportu sali. Wpisane przez osoby wyznaczone
// w grafiku. Gotówka sfiskalizowana + karta z imprez liczą się jako IMP (minus w rozliczeniu dnia).
const iso = (d) => d.toISOString().slice(0, 10)
const zl = (n) => (n || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const FORMA = { gotowka: 'Gotówka', karta: 'Karta', przelew: 'Przelew' }

export default function RejestrImprez() {
  const { toast } = useToast()
  const [od, setOd] = useState(iso(new Date(Date.now() - 30 * 86400000)))
  const [doDnia, setDoDnia] = useState(iso(new Date()))
  const [dane, setDane] = useState({ rozliczenia: [], razem: {} })
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setDane(await api(`/imprezy/rozliczenia?start=${od}&end=${doDnia}`))
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [od, doDnia, toast])

  useEffect(() => { load() }, [load])

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader title="Rejestr imprez" subtitle="Rozliczenia imprez wpisane przez osoby wyznaczone w grafiku. Osobno od raportu sali; gotówka sfiskalizowana i karta z imprez wchodzą do IMP." />

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5"><span className="field-label">Od</span>
          <input type="date" value={od} onChange={(e) => setOd(e.target.value)} className="field" /></label>
        <label className="flex flex-col gap-1.5"><span className="field-label">Do</span>
          <input type="date" value={doDnia} onChange={(e) => setDoDnia(e.target.value)} className="field" /></label>
        <div className="ml-auto text-right text-xs text-muted">
          Razem: <b className="text-ink">{zl(dane.razem?.suma_gotowka)}</b> got. ·
          <b className="text-ink"> {zl(dane.razem?.suma_karta)}</b> karta ·
          <b className="text-ink"> {zl(dane.razem?.suma_przelew)}</b> przelew
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-12"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : dane.rozliczenia.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] p-8 text-center text-sm text-muted">Brak rozliczeń imprez w tym zakresie.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {dane.rozliczenia.map((r) => (
            <div key={r.id} className="rounded-2xl border border-line bg-white/[0.02] p-4">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-bold text-ink">{r.opis || 'Impreza'}</span>
                <span className="font-mono text-xs text-muted">{ddmmyyyy(r.data)}</span>
              </div>
              <div className="mb-2 text-xs text-muted">{r.pracownik || '—'}</div>
              <div className="space-y-1">
                {r.pozycje.map((p, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg bg-surface-2 px-2.5 py-1.5 text-sm">
                    <span className="font-semibold text-ink">
                      {FORMA[p.forma] || p.forma}
                      {p.forma === 'gotowka' && <span className={`ml-1.5 text-[11px] font-normal ${p.sfiskalizowane ? 'text-success' : 'text-muted'}`}>{p.sfiskalizowane ? '✓ sfiskal.' : 'niefiskal.'}</span>}
                    </span>
                    <span className="font-mono text-ink">{p.forma === 'przelew' ? '— (admin)' : zl(p.kwota)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
