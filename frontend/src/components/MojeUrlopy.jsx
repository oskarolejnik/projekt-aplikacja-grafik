import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from './ui/Card'
import { Button } from './ui/Button'
import { Spinner } from './ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from './ui/Toast'
import { ddmmyyyy } from '../lib/format'

// Urlopy pracownika obsługi — sekcja w „Dyspozycyjności". Wniosek (od–do + powód opcjonalny),
// lista własnych wniosków ze statusem, wycofanie oczekującego. Zaakceptowany urlop blokuje
// auto-przydział i jest widoczny obok dyspozycji.
const STATUS = {
  oczekuje: { label: 'Oczekuje', cls: 'bg-lemon/15 text-lemon' },
  zaakceptowany: { label: 'Zaakceptowany', cls: 'bg-success/15 text-success' },
  odrzucony: { label: 'Odrzucony', cls: 'bg-danger/15 text-danger' },
}

export default function MojeUrlopy() {
  const { toast, confirm } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ start: '', koniec: '', powod: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setLista((await api('/me/urlopy')).urlopy || [])
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const zloz = async () => {
    if (!form.start || !form.koniec) { toast('Podaj zakres dat.', 'error'); return }
    if (form.koniec < form.start) { toast('Koniec nie może być przed początkiem.', 'error'); return }
    setBusy(true)
    try {
      await api('/me/urlopy', 'POST', { start: form.start, koniec: form.koniec, powod: form.powod.trim() || null })
      toast('Wniosek wysłany.', 'success')
      setForm({ start: '', koniec: '', powod: '' })
      load()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const wycofaj = async (u) => {
    if (!(await confirm('Wycofać wniosek urlopowy?'))) return
    try {
      await api(`/me/urlopy/${u.id}`, 'DELETE')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  return (
    <Card className="mt-6 p-6">
      <SectionHeader title="Urlopy" subtitle="Złóż wniosek — administrator go zaakceptuje lub odrzuci. Powód jest opcjonalny." />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Od</span>
          <input type="date" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} className="field" />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Do</span>
          <input type="date" value={form.koniec} onChange={(e) => setForm({ ...form, koniec: e.target.value })} className="field" />
        </label>
        <label className="flex flex-1 flex-col gap-1.5">
          <span className="field-label">Powód (opcjonalnie)</span>
          <input value={form.powod} onChange={(e) => setForm({ ...form, powod: e.target.value })} placeholder="np. wakacje" className="field" />
        </label>
        <Button onClick={zloz} disabled={busy}>
          <Icon name="plus" className="h-4 w-4" /> Złóż wniosek
        </Button>
      </div>

      <div className="mt-5">
        {loading ? (
          <div className="grid place-items-center py-6"><Spinner className="h-5 w-5 text-muted" /></div>
        ) : lista.length === 0 ? (
          <p className="py-2 text-sm text-muted">Brak wniosków.</p>
        ) : (
          <div className="space-y-2">
            {lista.map((u) => {
              const s = STATUS[u.status] || STATUS.oczekuje
              return (
                <div key={u.id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white/[0.02] p-3">
                  <div className="min-w-0">
                    <div className="font-semibold text-ink">{ddmmyyyy(u.start)} – {ddmmyyyy(u.koniec)}</div>
                    {u.powod && <div className="truncate text-xs text-muted">{u.powod}</div>}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${s.cls}`}>{s.label}</span>
                    {u.status === 'oczekuje' && (
                      <button onClick={() => wycofaj(u)} className="rounded-lg border border-danger/20 bg-danger/10 p-1.5 text-danger transition hover:bg-danger/20" title="Wycofaj wniosek">
                        <Icon name="trash" className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Card>
  )
}
