import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { num } from '../../lib/num'
import { useToast } from '../ui/Toast'

// Zeszyt kasowy — PRZYCHÓD (SALA z rozliczenia + imprezy auto + ręczne wiersze) − ROZCHÓD
// (Towar/Koszty/Wypłaty/Inne) → STAN (saldo gotówki narastająco). Admin edytuje; szef czyta.
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const KOL = [{ v: 'towar', l: 'Towar' }, { v: 'koszty', l: 'Koszty' }, { v: 'wyplaty', l: 'Wypłaty' }, { v: 'inne', l: 'Inne' }]
const KOL_L = Object.fromEntries(KOL.map((k) => [k.v, k.l]))
const dz = (s) => { const [, m, d] = s.split('-'); return `${d}.${m}` }
const miesiacTeraz = () => new Date().toISOString().slice(0, 7)
const granice = (mc) => { const [y, m] = mc.split('-').map(Number); const ost = new Date(y, m, 0).getDate(); return [`${mc}-01`, `${mc}-${String(ost).padStart(2, '0')}`] }
const cellInp = 'w-20 rounded-md border border-line bg-surface px-2 py-1 text-right text-xs text-ink outline-none focus:border-mint'

export default function Zeszyt({ readOnly = false, endpoint = '/zeszyt' }) {
  const { toast } = useToast()
  const [mc, setMc] = useState(miesiacTeraz())
  const [dane, setDane] = useState(null)
  const [loading, setLoading] = useState(true)
  const [formR, setFormR] = useState({})        // per-dzień formularz rozchodu
  const [formP, setFormP] = useState({})         // per-dzień formularz przychodu
  const [rozwiniete, setRozwiniete] = useState(() => new Set())   // dni odsłonięte ręcznie (puste)
  const [cfg, setCfg] = useState({ stan_poczatkowy: '', stan_poczatkowy_data: '' })

  const load = useCallback(async () => {
    setLoading(true)
    const [start, end] = granice(mc)
    try {
      const d = await api(`${endpoint}?start=${start}&end=${end}`)
      setDane(d)
      setCfg({ stan_poczatkowy: d.stan_poczatkowy ?? '', stan_poczatkowy_data: d.stan_poczatkowy_data || '' })
    } catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [mc, endpoint, toast])

  useEffect(() => { load() }, [load])

  const zapiszCfg = async () => {
    try {
      await api('/zeszyt/config', 'PUT', { stan_poczatkowy: num(cfg.stan_poczatkowy), stan_poczatkowy_data: cfg.stan_poczatkowy_data || null })
      toast('Zapisano stan początkowy.', 'success'); load()
    } catch (e) { toast(e.message, 'error') }
  }

  const dodajRozchod = async (data) => {
    const f = formR[data] || {}
    if (!num(f.kwota)) { toast('Podaj kwotę rozchodu.', 'error'); return }
    try {
      await api('/zeszyt/pozycja', 'POST', { data, kolumna: f.kolumna || 'towar', opis: f.opis || null, kwota: num(f.kwota) })
      setFormR((s) => ({ ...s, [data]: { kolumna: f.kolumna || 'towar' } })); load()
    } catch (e) { toast(e.message, 'error') }
  }
  const usunRozchod = async (id) => { try { await api(`/zeszyt/pozycja/${id}`, 'DELETE'); load() } catch (e) { toast(e.message, 'error') } }
  const setPrzelewSala = async (data, kwota) => {
    try { await api(`/rozliczenie/przelew?data=${data}&przelew=${num(kwota)}`, 'PUT'); load() }
    catch (e) { toast(e.message, 'error') }
  }

  const dodajPrzychod = async (data) => {
    const f = formP[data] || {}
    if (!num(f.gotowka) && !num(f.terminal) && !num(f.przelew) && !num(f.impreza)) { toast('Podaj kwotę przychodu.', 'error'); return }
    try {
      await api('/zeszyt/przychod', 'POST', { data, zrodlo: f.zrodlo || null, gotowka: num(f.gotowka), terminal: num(f.terminal), przelew: num(f.przelew), impreza: num(f.impreza) })
      setFormP((s) => ({ ...s, [data]: {} })); load()
    } catch (e) { toast(e.message, 'error') }
  }
  const usunPrzychod = async (id) => { try { await api(`/zeszyt/przychod/${id}`, 'DELETE'); load() } catch (e) { toast(e.message, 'error') } }

  const setFR = (data, patch) => setFormR((s) => ({ ...s, [data]: { ...(s[data] || {}), ...patch } }))
  const setFP = (data, patch) => setFormP((s) => ({ ...s, [data]: { ...(s[data] || {}), ...patch } }))

  const wszystkie = dane?.dni || []
  const stanKoniec = wszystkie.length ? wszystkie[wszystkie.length - 1].stan : (dane?.stan_poczatkowy ?? 0)
  const aktywny = (d) => d.wiersze.length || d.rozchod.length
  // admin widzi wszystkie dni (puste zwinięte); szef tylko dni z ruchem
  const dniWidoczne = readOnly ? wszystkie.filter(aktywny) : wszystkie
  const otwarty = (d) => aktywny(d) || rozwiniete.has(d.data)

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <SectionHeader title="Zeszyt kasowy" subtitle="Przychód (sala + imprezy + ręczne wpisy) − rozchód = stan gotówki narastająco." />
        <input type="month" value={mc} onChange={(e) => setMc(e.target.value)} className="field" />
      </div>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface-2 p-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold text-ink">Stan początkowy</span>
          {readOnly ? (
            <span className="font-mono text-ink">{zl(cfg.stan_poczatkowy)}{cfg.stan_poczatkowy_data ? ` (od ${cfg.stan_poczatkowy_data})` : ''}</span>
          ) : (
            <>
              <input value={cfg.stan_poczatkowy} onChange={(e) => setCfg((c) => ({ ...c, stan_poczatkowy: e.target.value }))} className="w-28 rounded-md border border-line bg-surface px-2 py-1 text-right text-sm text-ink outline-none focus:border-mint" />
              <span className="text-muted">od</span>
              <input type="date" value={cfg.stan_poczatkowy_data || ''} onChange={(e) => setCfg((c) => ({ ...c, stan_poczatkowy_data: e.target.value }))} className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink outline-none focus:border-mint" />
              <button onClick={zapiszCfg} className="rounded-md border border-line px-2 py-1 text-xs font-semibold text-mint">zapisz</button>
            </>
          )}
        </div>
        <div className="text-sm"><span className="text-muted">Stan na koniec okresu: </span><span className="font-mono text-lg font-bold text-mint">{zl(stanKoniec)}</span></div>
      </div>

      {loading || !dane ? (
        <div className="grid place-items-center py-12"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : dniWidoczne.length === 0 ? (
        <p className="rounded-xl border border-line bg-white/[0.02] p-6 text-center text-muted">Brak ruchu w tym miesiącu.</p>
      ) : (
        <div className="space-y-2">
          {dniWidoczne.map((d) => {
            const open = otwarty(d)
            const fr = formR[d.data] || {}; const fp = formP[d.data] || {}
            return (
              <div key={d.data} className={`rounded-xl border border-line ${open ? 'bg-white/[0.02] p-3' : 'px-3 py-1.5'}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-sm font-bold text-ink">{dz(d.data)}</span>
                    {!open && !readOnly && (
                      <button onClick={() => setRozwiniete((s) => new Set([...s, d.data]))} className="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-[11px] font-semibold text-mint"><Icon name="plus" className="h-3 w-3" /> dodaj</button>
                    )}
                  </div>
                  <span className="text-sm"><span className="text-muted">STAN </span><span className="font-mono font-bold text-mint">{zl(d.stan)}</span></span>
                </div>

                {open && (
                  <>
                    {/* PRZYCHÓD */}
                    <div className="mt-2 overflow-x-auto">
                      <table className="w-full min-w-[460px] text-sm">
                        <thead>
                          <tr className="text-[10px] uppercase tracking-wide text-muted/70">
                            <th className="px-2 py-1 text-left font-bold">Źródło</th>
                            <th className="px-2 py-1 text-right font-bold">Gotówka</th>
                            <th className="px-2 py-1 text-right font-bold">Terminal</th>
                            <th className="px-2 py-1 text-right font-bold">Przelew</th>
                            <th className="px-2 py-1 text-right font-bold">Impreza</th>
                          </tr>
                        </thead>
                        <tbody>
                          {d.wiersze.map((w, i) => (
                            <tr key={i} className="border-t border-line/40">
                              <td className="px-2 py-1 font-semibold text-ink">
                                {w.zrodlo}
                                {!readOnly && w.manualny && <button onClick={() => usunPrzychod(w.id)} title="Usuń wiersz" className="ml-1.5 align-middle text-danger">×</button>}
                              </td>
                              <td className="px-2 py-1 text-right font-mono">{zl(w.gotowka)}</td>
                              <td className="px-2 py-1 text-right font-mono text-muted">{zl(w.terminal)}</td>
                              <td className="px-2 py-1 text-right font-mono text-muted">
                                {!readOnly && w.sala_id ? (
                                  <input defaultValue={w.przelew || ''} placeholder="0" title="Przelew z palca"
                                    onBlur={(e) => { if (num(e.target.value) !== (w.przelew || 0)) setPrzelewSala(d.data, e.target.value) }}
                                    className="w-20 rounded-md border border-line bg-surface px-2 py-0.5 text-right text-xs text-ink outline-none focus:border-mint" />
                                ) : zl(w.przelew)}
                              </td>
                              <td className="px-2 py-1 text-right font-mono">{zl(w.impreza)}</td>
                            </tr>
                          ))}
                          {d.wiersze.length === 0 && <tr><td colSpan={5} className="px-2 py-1 text-xs text-muted">Brak przychodu.</td></tr>}
                        </tbody>
                      </table>
                    </div>
                    {!readOnly && (
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <input placeholder="źródło (np. Autobus)" value={fp.zrodlo || ''} onChange={(e) => setFP(d.data, { zrodlo: e.target.value })} className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none" />
                        <input placeholder="got." value={fp.gotowka || ''} onChange={(e) => setFP(d.data, { gotowka: e.target.value })} className={cellInp} />
                        <input placeholder="term." value={fp.terminal || ''} onChange={(e) => setFP(d.data, { terminal: e.target.value })} className={cellInp} />
                        <input placeholder="przel." value={fp.przelew || ''} onChange={(e) => setFP(d.data, { przelew: e.target.value })} className={cellInp} />
                        <input placeholder="impr." value={fp.impreza || ''} onChange={(e) => setFP(d.data, { impreza: e.target.value })} className={cellInp} />
                        <button onClick={() => dodajPrzychod(d.data)} className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs font-semibold text-mint"><Icon name="plus" className="h-3 w-3" /> przychód</button>
                      </div>
                    )}

                    {/* ROZCHÓD */}
                    <div className="mt-2 border-t border-line/40 pt-2">
                      {d.rozchod.map((p) => (
                        <div key={p.id} className="flex items-center gap-2 py-0.5 text-sm">
                          <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-bold uppercase text-muted">{KOL_L[p.kolumna] || p.kolumna}</span>
                          <span className="min-w-0 flex-1 truncate text-ink">{p.opis || '—'}</span>
                          <span className="font-mono text-danger">− {zl(p.kwota)}</span>
                          {!readOnly && <button onClick={() => usunRozchod(p.id)} className="rounded border border-danger/20 bg-danger/10 p-1 text-danger"><Icon name="trash" className="h-3 w-3" /></button>}
                        </div>
                      ))}
                      {!readOnly && (
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          <select value={fr.kolumna || 'towar'} onChange={(e) => setFR(d.data, { kolumna: e.target.value })} className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none">
                            {KOL.map((k) => <option key={k.v} value={k.v}>{k.l}</option>)}
                          </select>
                          <input placeholder="opis" value={fr.opis || ''} onChange={(e) => setFR(d.data, { opis: e.target.value })} className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none" />
                          <input placeholder="kwota" value={fr.kwota || ''} onChange={(e) => setFR(d.data, { kwota: e.target.value })} className={cellInp} />
                          <button onClick={() => dodajRozchod(d.data)} className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs font-semibold text-danger"><Icon name="plus" className="h-3 w-3" /> rozchód</button>
                        </div>
                      )}
                    </div>

                    <div className="mt-2 flex justify-end gap-4 text-xs text-muted">
                      <span>przychód gotówka <b className="text-ink">{zl(d.przychod_gotowka)}</b></span>
                      <span>rozchód <b className="text-danger">{zl(d.rozchod_suma)}</b></span>
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
