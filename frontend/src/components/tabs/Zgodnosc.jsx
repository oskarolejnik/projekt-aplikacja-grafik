import { useEffect, useState, useCallback } from 'react'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { Card, SectionHeader } from '../ui/Card'
import { Hint } from '../ui/Hint'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'

// Zgodność lokalu (roadmapa v2, oś B): badania/dokumenty załogi + terminy lokalu
// (koncesja alkoholowa i jej raty, przeglądy). Statusy liczone na backendzie
// (przeterminowane / pilne ≤14 dni / wkrótce ≤30 / ok). Dokument z „blokuje grafik"
// po terminie wyklucza pracownika z auto-przydziału i świeci ostrzeżeniem w Grafiku.

const TYPY = {
  badania_sanepid: 'Badania sanepid',
  medycyna_pracy: 'Medycyna pracy',
  szkolenie_bhp: 'Szkolenie BHP',
  koncesja: 'Koncesja',
  przeglad: 'Przegląd',
  inne: 'Inne',
}
const TYPY_PRACOWNIKA = ['badania_sanepid', 'medycyna_pracy', 'szkolenie_bhp', 'inne']
const TYPY_LOKALU = ['koncesja', 'przeglad', 'inne']

const STATUS_BADGE = {
  przeterminowane: 'bg-danger/15 text-danger',
  pilne: 'bg-coral/15 text-coral',
  wkrotce: 'bg-lemon/15 text-lemon',
  ok: 'bg-white/[0.04] text-muted',
}

const dniLabel = (d) => (d < 0 ? `${-d} dni po terminie` : d === 0 ? 'dziś' : `za ${d} dni`)

const PUSTY = { pracownik_id: '', typ: 'badania_sanepid', nazwa: '', data_waznosci: '', notatka: '', blokuje_grafik: true }

export default function Zgodnosc() {
  const { pracownicy } = useData()
  const { toast, confirm } = useToast()
  const [dokumenty, setDokumenty] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(null)          // null = formularz schowany; obiekt = edycja/dodawanie
  const [edytowaneId, setEdytowaneId] = useState(null)
  const [zapis, setZapis] = useState(false)

  const load = useCallback(async () => {
    try {
      setDokumenty(await api('/zgodnosc'))
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const otworzNowy = (dlaPracownika) => {
    setEdytowaneId(null)
    setForm({ ...PUSTY, typ: dlaPracownika ? 'badania_sanepid' : 'koncesja', pracownik_id: dlaPracownika ? (pracownicy[0]?.id ?? '') : '', blokuje_grafik: dlaPracownika })
  }

  const otworzEdycje = (d) => {
    setEdytowaneId(d.id)
    setForm({
      pracownik_id: d.pracownik_id ?? '',
      typ: d.typ, nazwa: d.nazwa, data_waznosci: d.data_waznosci,
      notatka: d.notatka || '', blokuje_grafik: d.blokuje_grafik,
    })
  }

  const zapisz = async () => {
    if (!form.nazwa.trim()) { toast('Podaj nazwę dokumentu.', 'error'); return }
    if (!form.data_waznosci) { toast('Podaj datę ważności.', 'error'); return }
    setZapis(true)
    const dane = {
      pracownik_id: form.pracownik_id === '' ? null : Number(form.pracownik_id),
      typ: form.typ, nazwa: form.nazwa.trim(), data_waznosci: form.data_waznosci,
      notatka: form.notatka.trim() || null, blokuje_grafik: form.blokuje_grafik,
    }
    try {
      if (edytowaneId) await api(`/zgodnosc/${edytowaneId}`, 'PUT', dane)
      else await api('/zgodnosc', 'POST', dane)
      toast(edytowaneId ? 'Zapisano zmiany.' : 'Dodano dokument.', 'success')
      setForm(null); setEdytowaneId(null)
      await load()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setZapis(false)
    }
  }

  const usun = async (d) => {
    if (!(await confirm(`Usunąć „${d.nazwa}"?`, { confirmText: 'Usuń' }))) return
    try {
      await api(`/zgodnosc/${d.id}`, 'DELETE')
      toast('Usunięto.', 'success')
      await load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const zaloga = dokumenty.filter((d) => d.pracownik_id != null)
  const lokal = dokumenty.filter((d) => d.pracownik_id == null)
  const uwaga = dokumenty.filter((d) => d.status !== 'ok').length
  const dlaPracownika = form && form.pracownik_id !== ''
  const fld = 'w-full min-w-0 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted focus:border-mint/60 focus:ring-2 focus:ring-mint/20'

  const Wiersz = ({ d }) => (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-ink">{d.nazwa}</span>
          {d.blokuje_grafik && (
            <span title="Po terminie blokuje auto-przydział w grafiku">
              <Icon name="warning" className={`h-3.5 w-3.5 shrink-0 ${d.status === 'przeterminowane' ? 'text-danger' : 'text-muted/60'}`} />
            </span>
          )}
        </div>
        <div className="text-xs text-muted">
          {TYPY[d.typ] || d.typ}{d.pracownik ? ` · ${d.pracownik}` : ''}{d.notatka ? ` · ${d.notatka}` : ''}
        </div>
      </div>
      <span className="text-xs tabular-nums text-muted">{d.data_waznosci}</span>
      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_BADGE[d.status]}`}>{dniLabel(d.dni)}</span>
      <div className="flex items-center gap-1">
        <button onClick={() => otworzEdycje(d)} className="rounded-lg p-2 text-muted transition hover:bg-white/[0.06] hover:text-ink" aria-label="Edytuj">
          <Icon name="clipboard" className="h-4 w-4" />
        </button>
        <button onClick={() => usun(d)} className="rounded-lg p-2 text-muted transition hover:bg-danger/10 hover:text-danger" aria-label="Usuń">
          <Icon name="trash" className="h-4 w-4" />
        </button>
      </div>
    </div>
  )

  if (loading) return <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Zgodność — badania i terminy"
        subtitle={uwaga > 0 ? `${uwaga} ${uwaga === 1 ? 'pozycja wymaga' : 'pozycje wymagają'} uwagi (≤30 dni lub po terminie).` : 'Wszystkie dokumenty i terminy aktualne.'}
      >
        <Button variant="ghost" onClick={() => otworzNowy(false)}><Icon name="office" className="h-4 w-4" /> Termin lokalu</Button>
        <Button onClick={() => otworzNowy(true)}><Icon name="plus" className="h-4 w-4" /> Dokument pracownika</Button>
      </SectionHeader>

      {form && (
        <Card className="p-6">
          <h3 className="font-display text-base font-semibold text-ink">
            {edytowaneId ? 'Edytuj pozycję' : dlaPracownika ? 'Nowy dokument pracownika' : 'Nowy termin lokalu'}
          </h3>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Dotyczy</span>
              <select value={form.pracownik_id} onChange={(e) => set('pracownik_id', e.target.value)} className={fld}>
                <option value="">— termin lokalu —</option>
                {pracownicy.map((p) => <option key={p.id} value={p.id}>{p.imie} {p.nazwisko}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Typ</span>
              <select value={form.typ} onChange={(e) => set('typ', e.target.value)} className={fld}>
                {(dlaPracownika ? TYPY_PRACOWNIKA : TYPY_LOKALU).map((t) => <option key={t} value={t}>{TYPY[t]}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1.5 md:col-span-2">
              <span className="field-label">Nazwa</span>
              <input value={form.nazwa} onChange={(e) => set('nazwa', e.target.value)} className={fld}
                     placeholder={dlaPracownika ? 'np. Orzeczenie sanitarno-epidemiologiczne' : 'np. Koncesja — II rata (31.05)'} />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Ważne do</span>
              <input type="date" value={form.data_waznosci} onChange={(e) => set('data_waznosci', e.target.value)} className={fld} />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Notatka (opcjonalnie)</span>
              <input value={form.notatka} onChange={(e) => set('notatka', e.target.value)} className={fld} placeholder="np. skan w segregatorze «Kadry»" />
            </label>
            {dlaPracownika && (
              <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-muted md:col-span-2">
                <input type="checkbox" checked={form.blokuje_grafik} onChange={(e) => set('blokuje_grafik', e.target.checked)}
                       className="h-4 w-4 rounded border-line bg-transparent accent-mint" />
                Po terminie blokuj auto-przydział (przeterminowane badania = nie wchodzi na zmianę)
              </label>
            )}
          </div>
          <div className="mt-5 flex justify-end gap-3">
            <Button variant="ghost" onClick={() => { setForm(null); setEdytowaneId(null) }}>Anuluj</Button>
            <Button onClick={zapisz} disabled={zapis}>{zapis ? <Spinner className="h-4 w-4" /> : null} Zapisz</Button>
          </div>
        </Card>
      )}

      <Card className="p-6">
        <h3 className="flex items-center gap-1.5 font-display text-base font-semibold text-ink">
          Badania i dokumenty załogi
          <Hint>Sanepid, medycyna pracy, BHP — z datą ważności per pracownik.</Hint>
        </h3>
        <div className="mt-3">
          {zaloga.length === 0
            ? <p className="py-6 text-center text-sm text-muted">Brak dokumentów — dodaj pierwsze badania, a Lokalo przypilnuje terminu.</p>
            : zaloga.map((d) => <Wiersz key={d.id} d={d} />)}
        </div>
      </Card>

      <Card className="p-6">
        <h3 className="flex items-center gap-1.5 font-display text-base font-semibold text-ink">
          Terminy lokalu
          <Hint>Koncesja alkoholowa (raty 31.01 / 31.05 / 30.09), przeglądy gaśnic, wentylacji.</Hint>
        </h3>
        <div className="mt-3">
          {lokal.length === 0
            ? <p className="py-6 text-center text-sm text-muted">Brak terminów — dodaj np. najbliższą ratę koncesji.</p>
            : lokal.map((d) => <Wiersz key={d.id} d={d} />)}
        </div>
      </Card>
    </div>
  )
}
