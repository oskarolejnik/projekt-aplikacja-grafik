import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'

// Zamówienia sprzątaczki — formularz zgłoszenia + lista własnych zamówień ze statusem.
// Zdjęcie jest opcjonalne i ZMNIEJSZANE w przeglądarce (max 1024 px, JPEG), żeby nie wysyłać
// kilkumegabajtowych plików z telefonu.
const STATUS = {
  nowe: { label: 'Nowe', cls: 'bg-white/[0.08] text-muted' },
  odczytane: { label: 'Odczytane', cls: 'bg-info/15 text-info' },
  zamowione: { label: 'Zamówione', cls: 'bg-success/15 text-success' },
}

function zmniejszZdjecie(file, max = 1024, quality = 0.7) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const img = new Image()
      img.onload = () => {
        let { width, height } = img
        if (width > max || height > max) {
          if (width >= height) { height = Math.round((height * max) / width); width = max }
          else { width = Math.round((width * max) / height); height = max }
        }
        const c = document.createElement('canvas')
        c.width = width; c.height = height
        c.getContext('2d').drawImage(img, 0, 0, width, height)
        resolve(c.toDataURL('image/jpeg', quality))
      }
      img.onerror = reject
      img.src = e.target.result
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export default function TechZamowienia() {
  const { toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ nazwa: '', ilosc: '', notatka: '', zdjecie: null })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setLista((await api('/me/zamowienia')).zamowienia || [])
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const wybierzZdjecie = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const data = await zmniejszZdjecie(file)
      setForm((f) => ({ ...f, zdjecie: data }))
    } catch {
      toast('Nie udało się wczytać zdjęcia.', 'error')
    }
  }

  const wyslij = async () => {
    if (!form.nazwa.trim()) { toast('Podaj nazwę produktu.', 'error'); return }
    setBusy(true)
    try {
      await api('/me/zamowienia', 'POST', {
        nazwa: form.nazwa.trim(), ilosc: form.ilosc.trim() || null,
        notatka: form.notatka.trim() || null, zdjecie: form.zdjecie,
      })
      toast('Zamówienie wysłane.', 'success')
      setForm({ nazwa: '', ilosc: '', notatka: '', zdjecie: null })
      load()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card className="mx-auto max-w-xl p-6 sm:p-8">
        <SectionHeader title="Nowe zamówienie" subtitle="Zgłoś produkt do zamówienia. Administrator dostanie powiadomienie." />
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Nazwa produktu *</span>
            <input value={form.nazwa} onChange={(e) => setForm({ ...form, nazwa: e.target.value })} placeholder="Np. Płyn do podłóg" className="field" />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Ilość</span>
            <input value={form.ilosc} onChange={(e) => setForm({ ...form, ilosc: e.target.value })} placeholder="Np. 2 szt, 5 l" className="field" />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Notatka</span>
            <textarea value={form.notatka} onChange={(e) => setForm({ ...form, notatka: e.target.value })} rows={2} placeholder="Opcjonalnie…" className="field resize-none" />
          </label>
          <div className="flex flex-col gap-1.5">
            <span className="field-label">Zdjęcie (opcjonalnie)</span>
            {form.zdjecie ? (
              <div className="flex items-center gap-3">
                <img src={form.zdjecie} alt="podgląd" className="h-16 w-16 rounded-lg border border-line object-cover" />
                <button onClick={() => setForm({ ...form, zdjecie: null })} className="text-xs font-semibold text-danger">Usuń zdjęcie</button>
              </div>
            ) : (
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-dashed border-line bg-surface-2 px-4 py-3 text-sm text-muted transition hover:text-ink">
                <Icon name="upload" className="h-4 w-4" /> Dodaj zdjęcie
                <input type="file" accept="image/*" capture="environment" onChange={wybierzZdjecie} className="hidden" />
              </label>
            )}
          </div>
          <Button onClick={wyslij} disabled={busy} className="w-full">
            <Icon name="check" className="h-4 w-4" /> Wyślij zamówienie
          </Button>
        </div>
      </Card>

      <Card className="mx-auto max-w-xl p-6 sm:p-8">
        <SectionHeader title="Moje zamówienia" subtitle="Status nadaje administrator." />
        {loading ? (
          <div className="grid place-items-center py-8"><Spinner className="h-6 w-6 text-muted" /></div>
        ) : lista.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted">Brak zamówień.</p>
        ) : (
          <div className="space-y-2">
            {lista.map((z) => {
              const s = STATUS[z.status] || STATUS.nowe
              return (
                <div key={z.id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white/[0.02] p-3">
                  <div className="min-w-0">
                    <div className="font-semibold text-ink">{z.nazwa}{z.ilosc ? <span className="font-normal text-muted"> · {z.ilosc}</span> : null}</div>
                    <div className="text-xs text-muted">{ddmmyyyy(z.utworzono_at?.slice(0, 10))}{z.ma_zdjecie ? ' · 📷' : ''}</div>
                  </div>
                  <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-bold ${s.cls}`}>{s.label}</span>
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </div>
  )
}
