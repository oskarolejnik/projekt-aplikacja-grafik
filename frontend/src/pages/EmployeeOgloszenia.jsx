import { useEffect, useState, useCallback } from 'react'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from '../components/ui/Toast'

// Ogłoszenia zespołowe — widok PRACOWNIKA: lista aktywnych komunikatów (przypięte na górze)
// z potwierdzeniem przeczytania. Mobile-first.
const dataPL = (iso) => (iso ? new Date(iso).toLocaleDateString('pl-PL', { day: '2-digit', month: 'short' }) : '')

export default function EmployeeOgloszenia({ onZmiana }) {
  const { toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)

  const load = useCallback(async () => {
    try {
      const r = await api('/me/ogloszenia')
      setLista(r.ogloszenia || [])
      onZmiana?.(r.nieprzeczytane || 0)
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast, onZmiana])
  useEffect(() => { load() }, [load])

  const potwierdz = async (o) => {
    setBusy(o.id)
    try {
      await api(`/me/ogloszenia/${o.id}/potwierdz`, 'POST')
      setLista((L) => L.map((x) => (x.id === o.id ? { ...x, przeczytane: true } : x)))
      onZmiana?.(lista.filter((x) => !x.przeczytane && x.id !== o.id).length)
    } catch (e) { toast(e.message, 'error') } finally { setBusy(null) }
  }

  if (loading) return <div className="grid place-items-center py-20"><Spinner className="h-6 w-6 text-muted" /></div>

  if (lista.length === 0) return (
    <div className="rounded-2xl border border-line bg-white/[0.03] p-10 text-center text-sm text-muted">
      <Icon name="bell" className="mx-auto mb-2 h-7 w-7 text-muted/60" />
      Brak ogłoszeń. Tu pojawią się komunikaty od managera.
    </div>
  )

  return (
    <div className="space-y-3">
      {lista.map((o) => (
        <div key={o.id} className={`rounded-2xl border p-4 transition ${o.przeczytane ? 'border-line bg-white/[0.02]' : 'border-mint/40 bg-mint/[0.06]'}`}>
          <div className="flex items-start gap-2">
            {o.przypiete && <Icon name="pin" className="mt-0.5 h-4 w-4 shrink-0 text-lemon" />}
            <div className="min-w-0 flex-1">
              <div className="font-display text-sm font-bold text-ink">{o.tytul}</div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{o.tresc}</p>
              <div className="mt-2 text-[11px] text-muted/70">{dataPL(o.utworzono_at)}{o.autor ? ` · ${o.autor}` : ''}</div>
            </div>
          </div>
          <div className="mt-3">
            {o.przeczytane ? (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-mint">
                <Icon name="check" className="h-4 w-4" /> Przeczytane
              </span>
            ) : (
              <button onClick={() => potwierdz(o)} disabled={busy === o.id}
                className="rounded-xl bg-accent-gradient px-4 py-2 text-sm font-bold text-bg shadow-glow transition active:scale-[0.97] disabled:opacity-60">
                {busy === o.id ? 'Zapisuję…' : 'Potwierdzam przeczytanie'}
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
