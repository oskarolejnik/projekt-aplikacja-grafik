import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'

// Urlopy — widok ADMINA. Lista wniosków (oczekujące najpierw), akceptacja/odrzucenie
// (push do pracownika). Zaakceptowany urlop blokuje auto-przydział.
const STATUS = {
  oczekuje: { label: 'Oczekuje', cls: 'bg-lemon/15 text-lemon' },
  zaakceptowany: { label: 'Zaakceptowany', cls: 'bg-success/15 text-success' },
  odrzucony: { label: 'Odrzucony', cls: 'bg-danger/15 text-danger' },
}

export default function Urlopy() {
  const { toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setLista((await api('/urlopy')).urlopy || [])
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const rozpatrz = async (u, status) => {
    try {
      await api(`/urlopy/${u.id}/status`, 'PUT', { status })
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const oczekujace = lista.filter((u) => u.status === 'oczekuje')

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader
        title="Urlopy"
        subtitle={`Wnioski pracowników obsługi. ${oczekujace.length ? `${oczekujace.length} do rozpatrzenia.` : 'Brak oczekujących.'} Zaakceptowany urlop blokuje auto-przydział.`}
      />
      {loading ? (
        <div className="grid place-items-center py-12"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : lista.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] p-8 text-center text-sm text-muted">Brak wniosków.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {lista.map((u) => {
            const s = STATUS[u.status] || STATUS.oczekuje
            return (
              <div key={u.id} className={`rounded-2xl border bg-white/[0.02] p-4 ${u.status === 'oczekuje' ? 'border-lemon/40' : 'border-line'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-base font-bold text-ink">{u.pracownik || '—'}</div>
                    <div className="mt-0.5 font-mono text-sm text-ink/90">{ddmmyyyy(u.start)} – {ddmmyyyy(u.koniec)}</div>
                    {u.powod && <div className="mt-1 text-xs text-muted">Powód: {u.powod}</div>}
                  </div>
                  <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-bold ${s.cls}`}>{s.label}</span>
                </div>
                {u.status === 'oczekuje' && (
                  <div className="mt-3 flex gap-2">
                    <Button size="sm" variant="accent" onClick={() => rozpatrz(u, 'zaakceptowany')}>
                      <Icon name="check" className="h-4 w-4" /> Zaakceptuj
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => rozpatrz(u, 'odrzucony')}>
                      <Icon name="close" className="h-4 w-4" /> Odrzuć
                    </Button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
