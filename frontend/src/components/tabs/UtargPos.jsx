import { useEffect, useState, useCallback, useRef } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { num } from '../../lib/num'
import { useToast } from '../ui/Toast'

// Utarg dnia — wspólny mianownik integracji POS (tor A z docs/POS-INTEGRACJA.md).
// Lokal bez podpiętego POS-a wpisuje utarg ręcznie albo wgrywa CSV; agent/konektor
// pisze w ten sam endpoint. Liczba rachunków zasila prognozę ruchu i obsady.
const iso = (d) => d.toISOString().slice(0, 10)
const zl = (n) => (n == null ? '—' : (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2 }) + ' zł')
const fld = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-mint'

// CSV: nagłówek opcjonalny; kolumny data;netto[;gotowka[;karta[;liczba_rachunkow]]];
// separator , lub ; — kwoty z polskim przecinkiem dziesiętnym też przechodzą (num()).
export function parsujCsvUtargu(tekst) {
  const wiersze = tekst.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  const dni = []
  const bledy = []
  for (const [i, linia] of wiersze.entries()) {
    // średnik jako główny separator; przecinek tylko, gdy nie wygląda na dziesiętny
    const kol = linia.includes(';') ? linia.split(';') : linia.split(',')
    const data = (kol[0] || '').trim()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(data)) {
      if (i === 0) continue                       // pierwszy wiersz bez daty = nagłówek
      bledy.push(`wiersz ${i + 1}: zła data „${data}"`)
      continue
    }
    const netto = num(kol[1])
    dni.push({
      data,
      netto,
      gotowka: kol[2]?.trim() ? num(kol[2]) : null,
      karta: kol[3]?.trim() ? num(kol[3]) : null,
      liczba_rachunkow: kol[4]?.trim() ? Math.round(num(kol[4])) : null,
    })
  }
  return { dni, bledy }
}

function swiezosc(isoStr) {
  if (!isoStr) return { tekst: 'nigdy', ok: false }
  const min = Math.round((Date.now() - new Date(isoStr + 'Z').getTime()) / 60000)
  if (min < 60) return { tekst: `${min} min temu`, ok: true }
  if (min < 60 * 24) return { tekst: `${Math.round(min / 60)} h temu`, ok: min < 120 }
  return { tekst: `${Math.round(min / 1440)} dni temu`, ok: false }
}

export default function UtargPos() {
  const { toast } = useToast()
  const [status, setStatus] = useState(null)
  const [dni, setDni] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ data: iso(new Date()), netto: '', gotowka: '', karta: '', liczba_rachunkow: '' })
  const plikRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const end = iso(new Date())
      const start = iso(new Date(Date.now() - 13 * 86400000))
      const [s, u] = await Promise.all([api('/pos/status'), api(`/pos/utarg-dnia?start=${start}&end=${end}`)])
      setStatus(s); setDni(u.dni)
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }))

  const zapiszReczny = async () => {
    if (!form.data || form.netto === '') { toast('Podaj datę i utarg netto.', 'error'); return }
    setBusy(true)
    try {
      await api('/pos/utarg-dnia', 'POST', {
        zrodlo: 'reczny',
        dni: [{
          data: form.data, netto: num(form.netto),
          gotowka: form.gotowka === '' ? null : num(form.gotowka),
          karta: form.karta === '' ? null : num(form.karta),
          liczba_rachunkow: form.liczba_rachunkow === '' ? null : Math.round(num(form.liczba_rachunkow)),
        }],
      })
      setForm((s) => ({ ...s, netto: '', gotowka: '', karta: '', liczba_rachunkow: '' }))
      await load(); toast('Zapisano utarg dnia.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const importujCsv = async (plik) => {
    if (!plik) return
    setBusy(true)
    try {
      const tekst = await plik.text()
      const { dni: sparsowane, bledy } = parsujCsvUtargu(tekst)
      if (!sparsowane.length) { toast('Nie znaleziono żadnego wiersza z datą YYYY-MM-DD.', 'error'); return }
      const r = await api('/pos/utarg-dnia', 'POST', { zrodlo: 'csv', dni: sparsowane })
      await load()
      toast(`Zaimportowano ${r.zapisane} dni z CSV${bledy.length ? ` (pominięto ${bledy.length} błędnych wierszy)` : ''}.`,
            bledy.length ? 'info' : 'success')
    } catch (e) { toast(e.message, 'error') }
    finally { setBusy(false); if (plikRef.current) plikRef.current.value = '' }
  }

  if (loading) {
    return <Card className="p-8"><div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div></Card>
  }

  return (
    <div className="space-y-5">
      {/* Zdrowie integracji: agenty + świeżość źródeł */}
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Integracja POS" subtitle="Źródła danych sprzedażowych tego lokalu. Agent lub konektor pisze w to samo API, co formularz poniżej." />
        <div className="mt-4 space-y-2">
          {(status?.agenty || []).map((a) => {
            const s = swiezosc(a.ostatni_sync)
            return (
              <div key={a.driver} className="rounded-xl border border-line bg-surface-2 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${s.ok ? 'bg-success' : 'bg-danger'}`} />
                  <span className="text-sm font-semibold text-ink">Agent {a.driver}</span>
                  {a.wersja && <span className="text-xs text-muted">v{a.wersja}</span>}
                  <span className="ml-auto text-xs text-muted">ostatni sync: {s.tekst}</span>
                </div>
                {!!(a.capabilities || []).length && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {a.capabilities.map((c) => <span key={c} className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[11px] text-muted">{c}</span>)}
                  </div>
                )}
                {!!(a.bledy || []).length && (
                  <p className="mt-1.5 rounded-md bg-danger/10 px-2 py-1 text-xs text-danger">{a.bledy[a.bledy.length - 1]}</p>
                )}
              </div>
            )
          })}
          {!(status?.agenty || []).length && (
            <p className="rounded-xl border border-line bg-white/[0.02] px-4 py-3 text-sm text-muted">
              Żaden agent POS nie zgłosił się jeszcze do tej instancji. Utarg możesz prowadzić
              ręcznie lub z pliku CSV — a gdy podepniesz agenta, dane wskoczą w to samo miejsce.
            </p>
          )}
        </div>
      </Card>

      {/* Ręczny wpis + CSV */}
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Utarg dnia" subtitle="Ręczny wpis (jeden dzień) albo import CSV: kolumny data;netto;gotówka;karta;liczba rachunków — nagłówek opcjonalny." />
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
          <label className="text-xs font-semibold text-muted">Data
            <input type="date" value={form.data} onChange={(e) => set('data', e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Utarg netto *
            <input value={form.netto} onChange={(e) => set('netto', e.target.value)} placeholder="np. 4250,50" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Gotówka
            <input value={form.gotowka} onChange={(e) => set('gotowka', e.target.value)} placeholder="opcjonalnie" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Karta
            <input value={form.karta} onChange={(e) => set('karta', e.target.value)} placeholder="opcjonalnie" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Rachunki (szt.)
            <input value={form.liczba_rachunkow} onChange={(e) => set('liczba_rachunkow', e.target.value)} placeholder="→ prognoza" className={fld} /></label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={zapiszReczny} disabled={busy}><Icon name="check" className="h-4 w-4" /> Zapisz dzień</Button>
          <input ref={plikRef} type="file" accept=".csv,text/csv" className="hidden"
                 onChange={(e) => importujCsv(e.target.files?.[0])} />
          <Button variant="ghost" onClick={() => plikRef.current?.click()} disabled={busy}>
            <Icon name="upload" className="h-4 w-4" /> Import CSV
          </Button>
          <span className="text-xs text-muted">Liczba rachunków zasila prognozę ruchu i sugerowaną obsadę.</span>
        </div>
      </Card>

      {/* Ostatnie 14 dni */}
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Ostatnie 14 dni" subtitle="Każde źródło ma własny wiersz na dzień — agent nie nadpisuje ręcznych wpisów i odwrotnie." />
        <div className="mt-4 overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="bg-surface-2 text-[11px] uppercase tracking-wide text-muted">
                <th className="px-3 py-2 text-left font-bold">Data</th>
                <th className="px-3 py-2 text-left font-bold">Źródło</th>
                <th className="px-3 py-2 text-right font-bold">Netto</th>
                <th className="px-3 py-2 text-right font-bold">Gotówka</th>
                <th className="px-3 py-2 text-right font-bold">Karta</th>
                <th className="px-3 py-2 text-right font-bold">Rachunki</th>
              </tr>
            </thead>
            <tbody>
              {dni.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-4 text-center text-muted">Brak utargów w ostatnich 14 dniach — dodaj pierwszy wpis powyżej.</td></tr>
              )}
              {dni.map((d) => (
                <tr key={`${d.data}|${d.zrodlo}`} className="border-t border-line/60">
                  <td className="px-3 py-1.5 font-semibold text-ink">{d.data}</td>
                  <td className="px-3 py-1.5"><span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-muted">{d.zrodlo}</span></td>
                  <td className="px-3 py-1.5 text-right font-mono text-ink">{zl(d.netto)}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-muted">{zl(d.gotowka)}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-muted">{zl(d.karta)}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-muted">{d.liczba_rachunkow ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
