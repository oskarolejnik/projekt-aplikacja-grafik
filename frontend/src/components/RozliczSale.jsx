import { useEffect, useState } from 'react'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from './ui/Toast'

// Modal „Rozlicz się" — kelner sali wpisuje/potwierdza gotówkę i kartę (prefill z Gastro).
// Dodatkowo: kto ZAMYKA REWIR dosyła terminale swojego rewiru, a kto ZAMYKA ZMIANĘ — raporty kas.
// Po „Prześlij raport" rozliczenie jest potwierdzone i przycisk na grafiku znika.
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const num = (v) => (v === '' || v == null ? 0 : parseFloat(v) || 0)

export default function RozliczSale({ data, onClose }) {
  const { toast } = useToast()
  const [info, setInfo] = useState(null)   // pełna odpowiedź GET
  const [form, setForm] = useState({ gotowka: '', karta: '' })
  const [terminale, setTerminale] = useState([])   // [{kwota}]
  const [kasy, setKasy] = useState([])              // [{kwota}]
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`/me/rozliczenie?data=${data}`)
      .then((r) => {
        setInfo(r)
        const w = r.wiersz || {}
        setForm({ gotowka: String(w.gotowka ?? ''), karta: String(w.karta ?? '') })
        setTerminale((r.terminale || []).map((p) => ({ kwota: String(p.kwota ?? '') })))
        setKasy((r.kasy || []).map((p) => ({ kwota: String(p.kwota ?? '') })))
      })
      .catch((e) => toast(e.message, 'error'))
  }, [data, toast])

  const przeslij = async () => {
    setBusy(true)
    try {
      await api(`/me/rozliczenie?data=${data}`, 'PUT', {
        gotowka: num(form.gotowka), karta: num(form.karta), kw: info?.wiersz?.kw || 0,
        terminale: info?.zamyka_rewir ? terminale.filter((t) => t.kwota !== '').map((t) => ({ kwota: num(t.kwota) })) : [],
        kasy: info?.zamyka ? kasy.filter((t) => t.kwota !== '').map((t) => ({ kwota: num(t.kwota) })) : [],
      })
      toast('Raport przesłany.', 'success')
      onClose(true)
    } catch (e) { toast(e.message, 'error') }
    finally { setBusy(false) }
  }

  const pole = 'w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-right font-mono text-lg text-ink outline-none focus:border-mint'
  const mini = 'w-28 rounded-md border border-line bg-surface px-2 py-1.5 text-right font-mono text-sm text-ink outline-none focus:border-mint'

  const Lista = ({ tytul, items, setItems }) => (
    <div className="rounded-xl border border-line bg-white/[0.02] p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wide text-ink">{tytul}</span>
        <button onClick={() => setItems((s) => [...s, { kwota: '' }])} className="inline-flex items-center gap-1 text-xs font-semibold text-mint"><Icon name="plus" className="h-3.5 w-3.5" /> dodaj</button>
      </div>
      <div className="space-y-1.5">
        {items.length === 0 && <p className="text-xs text-muted">Dodaj kwoty z wydruków.</p>}
        {items.map((t, i) => (
          <div key={i} className="flex items-center justify-end gap-2">
            <input type="number" inputMode="decimal" value={t.kwota} onChange={(e) => setItems((s) => s.map((x, j) => (j === i ? { kwota: e.target.value } : x)))} placeholder="kwota" className={mini} />
            <button onClick={() => setItems((s) => s.filter((_, j) => j !== i))} className="rounded-lg border border-danger/20 bg-danger/10 p-1.5 text-danger"><Icon name="trash" className="h-3.5 w-3.5" /></button>
          </div>
        ))}
      </div>
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => onClose(false)}>
      <div className="material max-h-[90dvh] w-full max-w-sm overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <div className="font-display text-lg font-bold text-ink">Rozlicz się</div>
            <div className="text-xs text-muted">Twój utarg na sali · {data}</div>
          </div>
          <button onClick={() => onClose(false)} className="text-muted transition hover:text-ink"><Icon name="close" className="h-5 w-5" /></button>
        </div>

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-bold uppercase tracking-wide text-muted">Gotówka</span>
            <input type="number" inputMode="decimal" value={form.gotowka} onChange={(e) => setForm((f) => ({ ...f, gotowka: e.target.value }))} placeholder="0,00" className={pole} />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-bold uppercase tracking-wide text-muted">Karta</span>
            <input type="number" inputMode="decimal" value={form.karta} onChange={(e) => setForm((f) => ({ ...f, karta: e.target.value }))} placeholder="0,00" className={pole} />
          </label>
          {info && (info.wiersz?.fv || 0) > 0 && (
            <div className="flex items-center justify-between rounded-xl border border-line bg-white/[0.02] px-3 py-2 text-sm">
              <span className="text-muted">FV (faktury, z systemu)</span>
              <span className="font-mono text-mint">{zl(info.wiersz.fv)}</span>
            </div>
          )}

          {info?.zamyka_rewir && (
            <Lista tytul={`Terminale${info.rewir ? ` — ${info.rewir}` : ''}`} items={terminale} setItems={setTerminale} />
          )}
          {info?.zamyka && (
            <Lista tytul="Kasy (raporty dobowe)" items={kasy} setItems={setKasy} />
          )}
        </div>

        <button onClick={przeslij} disabled={busy} className="mt-5 w-full rounded-xl bg-cream py-3 text-sm font-semibold text-bg transition hover:bg-white disabled:opacity-50">
          Prześlij raport
        </button>
      </div>
    </div>
  )
}
