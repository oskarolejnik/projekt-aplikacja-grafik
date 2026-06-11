import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'

// Zamówienia sprzątaczki — widok ADMINA. Lista wszystkich zgłoszeń + zmiana statusu
// (Odczytane → Zamówione, każda wysyła push do autorki). Zdjęcie pobierane na żądanie.
const STATUS = {
  nowe: { label: 'Nowe', cls: 'bg-coral/15 text-coral' },
  odczytane: { label: 'Odczytane', cls: 'bg-info/15 text-info' },
  zamowione: { label: 'Zamówione', cls: 'bg-success/15 text-success' },
}

export default function Zamowienia() {
  const { toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [zdjecia, setZdjecia] = useState({}) // id -> dataURL (po kliknięciu)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setLista((await api('/zamowienia')).zamowienia || [])
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const zmienStatus = async (z, status) => {
    try {
      await api(`/zamowienia/${z.id}/status`, 'PUT', { status })
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const pokazZdjecie = async (z) => {
    if (zdjecia[z.id]) { setZdjecia((m) => ({ ...m, [z.id]: null })); return } // toggle off
    try {
      const r = await api(`/zamowienia/${z.id}/zdjecie`)
      setZdjecia((m) => ({ ...m, [z.id]: r.zdjecie }))
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader title="Zamówienia sprzątaczki" subtitle={'Zgłoszenia produktów. Oznacz „Odczytane", a po zakupie „Zamówione" — autorka dostanie powiadomienie.'} />
      {loading ? (
        <div className="grid place-items-center py-12"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : lista.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] p-8 text-center text-sm text-muted">Brak zamówień.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {lista.map((z) => {
            const s = STATUS[z.status] || STATUS.nowe
            return (
              <div key={z.id} className="rounded-2xl border border-line bg-white/[0.02] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-base font-bold text-ink">
                      {z.nazwa}{z.ilosc ? <span className="font-normal text-muted"> · {z.ilosc}</span> : null}
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {z.pracownik || '—'} · {ddmmyyyy(z.utworzono_at?.slice(0, 10))}
                    </div>
                  </div>
                  <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-bold ${s.cls}`}>{s.label}</span>
                </div>

                {z.notatka && <p className="mt-2 rounded-lg bg-surface-2 p-2 text-sm text-ink/90">{z.notatka}</p>}

                {z.ma_zdjecie && (
                  <div className="mt-2">
                    <button onClick={() => pokazZdjecie(z)} className="inline-flex items-center gap-1.5 text-xs font-semibold text-mint">
                      <Icon name="pin" className="h-3.5 w-3.5" /> {zdjecia[z.id] ? 'Ukryj zdjęcie' : 'Pokaż zdjęcie'}
                    </button>
                    {zdjecia[z.id] && <img src={zdjecia[z.id]} alt="zdjęcie zamówienia" className="mt-2 max-h-64 rounded-xl border border-line object-contain" />}
                  </div>
                )}

                <div className="mt-3 flex gap-2">
                  {z.status === 'nowe' && (
                    <Button size="sm" variant="ghost" onClick={() => zmienStatus(z, 'odczytane')}>
                      <Icon name="check" className="h-4 w-4" /> Odczytane
                    </Button>
                  )}
                  {z.status !== 'zamowione' && (
                    <Button size="sm" variant="accent" onClick={() => zmienStatus(z, 'zamowione')}>
                      <Icon name="check" className="h-4 w-4" /> Zamówione
                    </Button>
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
