import { useEffect, useState } from 'react'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from './ui/Toast'

// Modal „Rozlicz imprezę" — dla osoby wyznaczonej w grafiku (rozlicza_imprize). Pozycje kwota+forma:
// Gotówka (z checkboxem „sfiskalizowane"), Karta, Przelew (przelew = tylko zaznaczenie, kwotę wpisuje
// admin). Upsert: zapis zastępuje wcześniejsze pozycje na ten dzień. Trafia do rejestru imprez.
const FORMY = [
  { v: 'gotowka', label: 'Gotówka' },
  { v: 'karta', label: 'Karta' },
  { v: 'przelew', label: 'Przelew' },
]

export default function RozliczImpreze({ data, rewir, onClose }) {
  const { toast } = useToast()
  const [pozycje, setPozycje] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`/me/imprezy/rozlicz?data=${data}`)
      .then((r) => setPozycje((r.pozycje || []).map((p) => ({ ...p, kwota: String(p.kwota ?? '') }))))
      .catch((e) => toast(e.message, 'error'))
  }, [data, toast])

  const dodaj = () => setPozycje((p) => [...p, { forma: 'gotowka', kwota: '', sfiskalizowane: false }])
  const zmien = (i, patch) => setPozycje((p) => p.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  const usun = (i) => setPozycje((p) => p.filter((_, j) => j !== i))

  const zapisz = async () => {
    setBusy(true)
    try {
      const body = {
        data,
        pozycje: pozycje.map((p) => ({
          forma: p.forma,
          kwota: p.forma === 'przelew' ? 0 : (parseFloat(p.kwota) || 0),
          sfiskalizowane: p.forma === 'gotowka' ? !!p.sfiskalizowane : false,
        })),
      }
      await api('/me/imprezy/rozlicz', 'POST', body)
      toast('Impreza rozliczona.', 'success')
      onClose(true)
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => onClose(false)}>
      <div className="w-full max-w-md rounded-2xl border border-line bg-bg-2 p-5 shadow-glow" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between">
          <div>
            <div className="font-display text-lg font-bold text-ink">Rozlicz imprezę</div>
            <div className="text-xs text-muted">{rewir || 'Impreza'} · {data}</div>
          </div>
          <button onClick={() => onClose(false)} className="text-muted transition hover:text-ink"><Icon name="close" className="h-5 w-5" /></button>
        </div>

        <div className="space-y-2">
          {pozycje.length === 0 && <p className="py-2 text-center text-sm text-muted">Dodaj pozycje płatności.</p>}
          {pozycje.map((p, i) => (
            <div key={i} className="flex items-center gap-2 rounded-xl border border-line bg-surface-2 p-2">
              <select value={p.forma} onChange={(e) => zmien(i, { forma: e.target.value })} className="rounded-md border border-line bg-surface p-1.5 text-sm text-ink">
                {FORMY.map((f) => <option key={f.v} value={f.v}>{f.label}</option>)}
              </select>
              {p.forma !== 'przelew' ? (
                <input type="number" inputMode="decimal" value={p.kwota} onChange={(e) => zmien(i, { kwota: e.target.value })} placeholder="kwota zł" className="w-24 rounded-md border border-line bg-surface p-1.5 text-sm text-ink" />
              ) : (
                <span className="flex-1 text-xs text-muted">kwotę wpisze admin</span>
              )}
              {p.forma === 'gotowka' && (
                <label className="flex items-center gap-1 text-xs text-ink">
                  <input type="checkbox" checked={!!p.sfiskalizowane} onChange={(e) => zmien(i, { sfiskalizowane: e.target.checked })} className="h-4 w-4 accent-mint" />
                  sfiskal.
                </label>
              )}
              <button onClick={() => usun(i)} className="ml-auto rounded-lg border border-danger/20 bg-danger/10 p-1.5 text-danger" aria-label="Usuń"><Icon name="trash" className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>

        <button onClick={dodaj} className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-mint">
          <Icon name="plus" className="h-4 w-4" /> Dodaj pozycję
        </button>

        <div className="mt-4 flex gap-2">
          <button onClick={zapisz} disabled={busy} className="flex-1 rounded-xl bg-cream py-2.5 text-sm font-bold uppercase tracking-[0.15em] text-bg transition hover:brightness-[1.03] disabled:opacity-50">Zapisz rozliczenie</button>
        </div>
      </div>
    </div>
  )
}
