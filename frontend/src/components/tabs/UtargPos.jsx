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

  // Kreator „Podłącz agenta": token pokazywany JEDEN raz + gotowy config.yaml.
  const [nowyToken, setNowyToken] = useState(null)
  const [driverWybrany, setDriverWybrany] = useState('gastro_mssql')

  const generujToken = async () => {
    if (status?.token_aktywny) {
      const zgoda = await window.confirm?.('Nowy token unieważni poprzedni — działający agent straci dostęp. Kontynuować?')
      if (zgoda === false) return
    }
    setBusy(true)
    try {
      const r = await api('/pos/token', 'POST')
      setNowyToken(r.token)
      setStatus((s) => ({ ...s, token_aktywny: true, token_od: r.utworzono }))
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const uniewaznijToken = async () => {
    setBusy(true)
    try {
      await api('/pos/token', 'DELETE')
      setNowyToken(null)
      setStatus((s) => ({ ...s, token_aktywny: false, token_od: null }))
      toast('Token unieważniony — agent straci dostęp od następnego żądania.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const pobierzConfig = () => {
    const yaml = [
      '# Konfiguracja agenta POS Lokalo — wygenerowana w panelu.',
      '# Na serwerze POS uzupełnij dostęp do bazy (konto TYLKO DO ODCZYTU).',
      '',
      'lokalo:',
      `  url: "${window.location.origin}"`,
      `  token: "${nowyToken}"`,
      '',
      'agent:',
      '  poll_sekundy: 300',
      '  okno_dni: 3',
      '',
      `driver: ${driverWybrany}`,
      '',
      `${driverWybrany}:`,
      '  database_url: "mssql+pymssql://czytelnik:haslo@localhost/gastro"',
      '  # SQL-e strumieni: wzory i opis kolumn w agent_lokalny/config.example.yaml',
    ].join('\n')
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'config.yaml'
    a.click()
    URL.revokeObjectURL(a.href)
  }

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

        {/* Kreator podłączenia agenta: token + gotowy config.yaml do pobrania. */}
        <div className="mt-5 rounded-xl border border-line bg-white/[0.02] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-bold text-ink">Podłącz agenta POS</span>
            {status?.token_aktywny && (
              <span className="rounded-full bg-mint/15 px-2.5 py-0.5 text-xs font-semibold text-mint">
                token aktywny{status.token_od ? ` od ${status.token_od.slice(0, 10)}` : ''}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Agent instalowany na serwerze POS czyta dane (tylko odczyt!) i wypycha je tutaj.
            Wygeneruj token, pobierz gotowy <code className="text-ink">config.yaml</code> i przekaż
            paczkę serwisantowi POS — na miejscu zostaje tylko wpisanie dostępu do bazy.
          </p>

          {nowyToken ? (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-semibold text-lemon">
                Zapisz token teraz — widzisz go tylko raz (w bazie zostaje wyłącznie skrót):
              </p>
              <code className="block break-all rounded-lg border border-mint/30 bg-mint/[0.07] px-3 py-2 text-xs text-ink">{nowyToken}</code>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => { navigator.clipboard?.writeText(nowyToken); toast('Skopiowano token.', 'success') }}>
                  Kopiuj token
                </Button>
                <Button variant="ghost" onClick={pobierzConfig}>
                  <Icon name="download" className="h-4 w-4" /> Pobierz config.yaml
                </Button>
              </div>
              <p className="text-xs text-muted">
                Dalej na serwerze POS: <code>pip install -r requirements.txt</code>, uzupełnij dostęp
                do bazy w config.yaml, test: <code>python agent_pos.py --raz</code> — a tu pojawi się heartbeat.
              </p>
            </div>
          ) : (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <label className="text-xs font-semibold text-muted">System POS
                <select value={driverWybrany} onChange={(e) => setDriverWybrany(e.target.value)} className={`${fld} mt-0.5 w-56`}>
                  <option value="gastro_mssql">Gastro (Softech/LSI, MS SQL)</option>
                  <option value="" disabled>SOGA (Firebird) — wkrótce</option>
                  <option value="" disabled>X2System (PostgreSQL) — wkrótce</option>
                  <option value="" disabled>Dotykačka (chmura) — wkrótce</option>
                </select>
              </label>
              <div className="flex gap-2 pt-4">
                <Button onClick={generujToken} disabled={busy}>
                  <Icon name="key" className="h-4 w-4" /> {status?.token_aktywny ? 'Wygeneruj nowy token' : 'Wygeneruj token agenta'}
                </Button>
                {status?.token_aktywny && (
                  <Button variant="ghost" onClick={uniewaznijToken} disabled={busy}>Unieważnij token</Button>
                )}
              </div>
            </div>
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
