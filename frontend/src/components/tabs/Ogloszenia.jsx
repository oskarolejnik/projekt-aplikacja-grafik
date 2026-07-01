import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Ogłoszenia zespołowe — widok MANAGERA: tworzenie/edycja/usuwanie + licznik odczytów
// (ilu pracowników potwierdziło przeczytanie) i podgląd „kto przeczytał".
const PUSTY = { tytul: '', tresc: '', przypiete: false, wazne_do: '' }
const inp = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none transition focus:border-mint'
const dataPL = (iso) => (iso ? new Date(iso).toLocaleDateString('pl-PL', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '')

export default function Ogloszenia() {
  const { toast, confirm } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(PUSTY)
  const [edid, setEdid] = useState(null)          // id edytowanego (null = tryb tworzenia)
  const [busy, setBusy] = useState(false)
  const [ktoOtwarty, setKtoOtwarty] = useState(null)   // id ogłoszenia z rozwiniętą listą „kto przeczytał"
  const [kto, setKto] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    try { setLista(await api('/ogloszenia')) }
    catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }))
  const reset = () => { setForm(PUSTY); setEdid(null) }

  const zapisz = async () => {
    if (!form.tytul.trim() || !form.tresc.trim()) { toast('Podaj tytuł i treść.', 'error'); return }
    setBusy(true)
    try {
      const body = { tytul: form.tytul.trim(), tresc: form.tresc.trim(),
        przypiete: !!form.przypiete, wazne_do: form.wazne_do || null }
      if (edid) await api(`/ogloszenia/${edid}`, 'PUT', body)
      else await api('/ogloszenia', 'POST', body)
      toast(edid ? 'Ogłoszenie zaktualizowane.' : 'Ogłoszenie opublikowane — poszło powiadomienie.', 'success')
      reset(); load()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const edytuj = (o) => {
    setEdid(o.id)
    setForm({ tytul: o.tytul, tresc: o.tresc, przypiete: o.przypiete, wazne_do: o.wazne_do || '' })
    setKtoOtwarty(null)
  }

  const usun = async (o) => {
    if (!(await confirm(`Usunąć ogłoszenie „${o.tytul}"?`))) return
    try { await api(`/ogloszenia/${o.id}`, 'DELETE'); toast('Usunięto.', 'success'); if (edid === o.id) reset(); load() }
    catch (e) { toast(e.message, 'error') }
  }

  const pokazKto = async (o) => {
    if (ktoOtwarty === o.id) { setKtoOtwarty(null); return }
    setKtoOtwarty(o.id); setKto([])
    try { setKto(await api(`/ogloszenia/${o.id}/potwierdzenia`)) } catch (e) { toast(e.message, 'error') }
  }

  return (
    <div className="space-y-6">
      {/* Formularz tworzenia / edycji */}
      <Card className="p-6 sm:p-8">
        <SectionHeader title={edid ? 'Edytuj ogłoszenie' : 'Nowe ogłoszenie'}
          subtitle="Komunikat trafi do wszystkich pracowników — z powiadomieniem push na telefon." />
        <div className="mt-4 space-y-3">
          <input className={inp} placeholder="Tytuł (np. Zmiana zasad rozliczania)" value={form.tytul}
            onChange={(e) => set('tytul', e.target.value)} maxLength={160} />
          <textarea className={`${inp} min-h-[7rem] resize-y`} placeholder="Treść ogłoszenia…"
            value={form.tresc} onChange={(e) => set('tresc', e.target.value)} />
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={form.przypiete} onChange={(e) => set('przypiete', e.target.checked)}
                className="h-4 w-4 accent-mint" />
              Przypnij na górze
            </label>
            <label className="flex items-center gap-2 text-sm text-muted">
              Ważne do:
              <input type="date" className="rounded-lg border border-line bg-surface px-2 py-1 text-ink outline-none focus:border-mint"
                value={form.wazne_do} onChange={(e) => set('wazne_do', e.target.value)} />
            </label>
          </div>
          <div className="flex items-center gap-2 pt-1">
            <Button onClick={zapisz} disabled={busy}>{busy ? 'Zapisuję…' : (edid ? 'Zapisz zmiany' : 'Opublikuj')}</Button>
            {edid && <button onClick={reset} className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:text-ink">Anuluj</button>}
          </div>
        </div>
      </Card>

      {/* Lista opublikowanych */}
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Opublikowane ogłoszenia" subtitle="Przypięte na górze. Licznik pokazuje, ilu pracowników potwierdziło przeczytanie." />
        {loading ? (
          <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
        ) : lista.length === 0 ? (
          <div className="mt-4 rounded-xl border border-line bg-surface-2 p-10 text-center text-sm text-muted">
            Brak ogłoszeń. Opublikuj pierwsze powyżej.
          </div>
        ) : (
          <ul className="mt-4 space-y-3">
            {lista.map((o) => (
              <li key={o.id} className="rounded-xl border border-line bg-surface-2 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {o.przypiete && <Icon name="pin" className="h-4 w-4 text-lemon" />}
                      <span className="font-display text-sm font-bold text-ink">{o.tytul}</span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{o.tresc}</p>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted/80">
                      <span>{dataPL(o.utworzono_at)}{o.autor ? ` · ${o.autor}` : ''}</span>
                      {o.wazne_do && <span>ważne do {o.wazne_do}</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button onClick={() => edytuj(o)} className="rounded-lg border border-line p-2 text-muted transition hover:text-ink" aria-label="Edytuj"><Icon name="clipboard" className="h-4 w-4" /></button>
                    <button onClick={() => usun(o)} className="rounded-lg border border-line p-2 text-muted transition hover:text-coral" aria-label="Usuń"><Icon name="trash" className="h-4 w-4" /></button>
                  </div>
                </div>
                <button onClick={() => pokazKto(o)}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-mint/10 px-3 py-1 text-xs font-semibold text-mint transition hover:bg-mint/20">
                  <Icon name="check" className="h-3.5 w-3.5" />
                  Przeczytało {o.liczba_potwierdzen}/{o.liczba_odbiorcow}
                </button>
                {ktoOtwarty === o.id && (
                  <div className="mt-2 rounded-lg border border-line bg-surface p-3 text-xs">
                    {kto.length === 0 ? <span className="text-muted">Nikt jeszcze nie potwierdził.</span> : (
                      <ul className="space-y-1">
                        {kto.map((k, i) => (
                          <li key={i} className="flex items-center justify-between gap-3 text-ink">
                            <span>{k.pracownik}</span>
                            <span className="text-muted">{dataPL(k.potwierdzono_at)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
