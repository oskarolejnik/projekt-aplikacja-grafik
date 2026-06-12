import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Rozliczenie dnia (sala) — widok ADMINA. Kelnerzy wpisują G/T (FV auto z Gastro, KW koryguje).
// Zadatek (KP) czytany GLOBALNIE z Gastro — admin rozbija go na gotówkę/kartę (do szefa idzie tylko
// „Gotówka: X, Karta: Y"). IMP auto z imprez (z możliwością nadpisania z palca).
const iso = (d) => d.toISOString().slice(0, 10)
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const num = (v) => (v === '' || v == null ? 0 : parseFloat(v) || 0)

// kolory różnic — czytelne pod daltonizm (etykieta + znak, nie tylko kolor)
function Roznica({ wartosc, etykieta }) {
  if (Math.abs(wartosc) < 0.005) return <span className="text-xs font-bold text-success">zgodne</span>
  return (
    <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${wartosc < 0 ? 'bg-danger text-white' : 'bg-success text-bg'}`}>
      {etykieta} {zl(Math.abs(wartosc))}
    </span>
  )
}

export default function RozliczenieDnia() {
  const { toast } = useToast()
  const [data, setData] = useState(iso(new Date()))
  const [roz, setRoz] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setRoz(await api(`/rozliczenie?data=${data}`)) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [data, toast])

  useEffect(() => { load() }, [load])

  const setRozPole = (patch) => setRoz((r) => ({ ...r, ...patch }))
  const setKelner = (i, patch) => setRoz((r) => ({ ...r, kelnerzy: r.kelnerzy.map((k, j) => (j === i ? { ...k, ...patch } : k)) }))
  const setPoz = (pole, i, patch) => setRoz((r) => ({ ...r, [pole]: r[pole].map((p, j) => (j === i ? { ...p, ...patch } : p)) }))
  const dodajPoz = (pole) => setRoz((r) => ({ ...r, [pole]: [...(r[pole] || []), { etykieta: '', kwota: '', rewir: '' }] }))
  const usunPoz = (pole, i) => setRoz((r) => ({ ...r, [pole]: r[pole].filter((_, j) => j !== i) }))

  const zapisz = async (przekaz = false) => {
    setBusy(true)
    try {
      const body = {
        zadatek_gotowka: num(roz.zadatek_gotowka), zadatek_karta: num(roz.zadatek_karta),
        imp_reczny: !!roz.imp_reczny, imp_gotowka: num(roz.imp_gotowka), imp_karta: num(roz.imp_karta),
        przelew: num(roz.przelew),
        kelnerzy: roz.kelnerzy.map((k) => ({
          pracownik_id: k.pracownik_id, gotowka: num(k.gotowka), karta: num(k.karta), fv: num(k.fv), kw: num(k.kw),
        })),
        terminale: (roz.terminale || []).map((p) => ({ etykieta: p.etykieta || null, kwota: num(p.kwota), rewir: p.rewir || null })),
        kasy: (roz.kasy || []).map((p) => ({ etykieta: p.etykieta || null, kwota: num(p.kwota), rewir: p.rewir || null })),
      }
      const zapisany = await api(`/rozliczenie?data=${data}`, 'PUT', body)
      setRoz(zapisany)
      if (przekaz) { await api(`/rozliczenie/przekaz-szef?data=${data}`, 'POST'); load(); toast('Przekazano do szefa.', 'success') }
      else toast('Zapisano i przeliczono.', 'success')
    } catch (e) { toast(e.message, 'error') }
    finally { setBusy(false) }
  }

  const w = roz?.wynik
  const inp = 'w-24 rounded-md border border-line bg-surface px-2 py-1 text-right text-sm text-ink outline-none focus:border-mint'
  const inpS = 'w-20 rounded-md border border-line bg-surface px-2 py-1 text-right text-sm text-ink outline-none focus:border-mint'

  // rozbicie zadatku vs KP w bazie
  const zadatekSuma = num(roz?.zadatek_gotowka) + num(roz?.zadatek_karta)
  const kpBaza = Number(roz?.kp_baza || 0)
  const zadatekNiezgodny = kpBaza > 0 && Math.abs(zadatekSuma - kpBaza) > 0.005

  // przy włączeniu „ręcznie" IMP — wstaw bieżące wartości auto, by było od czego startować
  const toggleImpReczny = (on) => {
    if (on && w) setRozPole({ imp_reczny: true, imp_gotowka: w.imp.gotowka_sfiskalizowana, imp_karta: w.imp.karta })
    else setRozPole({ imp_reczny: false })
  }

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Rozliczenie dnia — sala" subtitle="Kelnerzy: G/T. FV auto z Gastro, KP (zadatki) globalnie z bazy, IMP z imprez. Zapisz, by przeliczyć." />
        <div className="flex items-center gap-2">
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} className="field" />
          {roz?.status === 'u_szefa'
            ? <span className="rounded-md bg-success/15 px-2 py-1 text-xs font-bold text-success">u szefa</span>
            : <span className="rounded-md bg-white/[0.06] px-2 py-1 text-xs font-bold text-muted">robocze</span>}
        </div>
      </div>

      {loading || !roz ? (
        <div className="grid place-items-center py-12"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : (
        <div className="space-y-6">
          {/* Kelnerzy — pełna szerokość, G/T/FV od razu widoczne (KW po prawej) */}
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="bg-surface-2 text-[11px] uppercase tracking-wide text-muted">
                  <th className="px-3 py-2 text-left font-bold">Kelner</th>
                  <th className="px-3 py-2 text-right font-bold">Gotówka (G)</th>
                  <th className="px-3 py-2 text-right font-bold">Karta (T)</th>
                  <th className="px-3 py-2 text-right font-bold text-mint">FV</th>
                  <th className="px-3 py-2 text-right font-bold text-muted/70">KW</th>
                </tr>
              </thead>
              <tbody>
                {roz.kelnerzy.length === 0 && (
                  <tr><td colSpan={5} className="px-3 py-3 text-center text-muted">Brak kelnerów na Sali tego dnia (sprawdź grafik).</td></tr>
                )}
                {roz.kelnerzy.map((k, i) => (
                  <tr key={k.pracownik_id} className="border-t border-line/60">
                    <td className="px-3 py-1.5 font-semibold text-ink">{k.pracownik}</td>
                    <td className="px-3 py-1.5 text-right"><input value={k.gotowka} onChange={(e) => setKelner(i, { gotowka: e.target.value })} className={inpS} /></td>
                    <td className="px-3 py-1.5 text-right"><input value={k.karta} onChange={(e) => setKelner(i, { karta: e.target.value })} className={inpS} /></td>
                    <td className="px-3 py-1.5 text-right"><input value={k.fv} onChange={(e) => setKelner(i, { fv: e.target.value })} className={`${inpS} text-mint`} /></td>
                    <td className="px-3 py-1.5 text-right"><input value={k.kw} onChange={(e) => setKelner(i, { kw: e.target.value })} className={`${inpS} text-muted`} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* LEWA: zadatek + utarg */}
            <div className="space-y-4">
              {/* Zadatek (KP) — globalnie z bazy, admin rozbija na gotówkę/kartę */}
              <div className="space-y-2 rounded-xl border border-line bg-surface-2 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-bold text-ink">Zadatek (KP)</span>
                  <span className="text-xs text-muted">suma KP (z Gastro): <b className="text-ink">{zl(kpBaza)}</b> — rozbij ręcznie</span>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-1.5 text-sm text-muted">gotówka<input value={roz.zadatek_gotowka} onChange={(e) => setRozPole({ zadatek_gotowka: e.target.value })} className={inpS} /></label>
                  <label className="flex items-center gap-1.5 text-sm text-muted">karta<input value={roz.zadatek_karta} onChange={(e) => setRozPole({ zadatek_karta: e.target.value })} className={inpS} /></label>
                </div>
                {zadatekNiezgodny && (
                  <p className="rounded-md bg-lemon/15 px-2 py-1 text-[11px] font-semibold text-lemon">Rozbicie {zl(zadatekSuma)} ≠ KP w bazie {zl(kpBaza)} — sprawdź podział.</p>
                )}
              </div>

              {/* Przelew z palca (admin) — poza kasą fiskalną; pokaże się też w Zeszycie i u szefa */}
              <label className="flex items-center justify-between gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2">
                <span className="text-sm font-semibold text-ink">Przelew <span className="text-xs font-normal text-muted">(z palca)</span></span>
                <input value={roz.przelew ?? ''} onChange={(e) => setRozPole({ przelew: e.target.value })} className={inpS} />
              </label>

              {/* UTARG — hero */}
              {w && (
                <>
                  <div className="rounded-xl border border-mint/40 bg-mint/[0.07] p-4 text-center">
                    <div className="text-[11px] font-bold uppercase tracking-wider text-mint/90">Utarg zafiskalizowany (sala)</div>
                    <div className="mt-1 font-display text-3xl font-bold text-ink">{zl(w.suma_zeszyt.razem)}</div>
                    <div className="mt-0.5 text-xs text-muted">gotówka {zl(w.suma_zeszyt.gotowka)} · karta {zl(w.suma_zeszyt.karta)}</div>
                  </div>
                  <div className="space-y-1.5 rounded-xl border border-line bg-white/[0.02] p-3 text-sm">
                    <div className="flex justify-between text-muted"><span>Zadatek (osobno)</span><span className="font-mono">{zl(w.zadatek)}</span></div>
                    <div className="flex flex-wrap justify-between gap-1"><span className="font-semibold text-ink">→ do szefa (utarg − zadatek)</span><span className="font-mono font-bold text-ink">G {zl(w.suma_szef.gotowka)} · K {zl(w.suma_szef.karta)}</span></div>
                    <div className="flex justify-between text-xs text-muted"><span>FV (faktury)</span><span className="font-mono text-mint">{zl(w.fv)}</span></div>
                    <div className="flex items-center justify-between border-t border-line/60 pt-1.5"><span className="font-bold text-ink">Brak / nadwyżka</span><Roznica wartosc={w.kasy.roznica} etykieta={w.kasy.roznica < 0 ? 'brak' : 'nadwyżka'} /></div>
                  </div>
                </>
              )}
            </div>

            {/* PRAWA: terminale + kasy + IMP */}
            <div className="space-y-4">
              {['terminale', 'kasy'].map((pole) => (
                <div key={pole} className="rounded-xl border border-line bg-white/[0.02] p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-bold uppercase tracking-wide text-ink">{pole === 'terminale' ? 'Terminale' : 'Kasy'}</span>
                    <button onClick={() => dodajPoz(pole)} className="inline-flex items-center gap-1 text-xs font-semibold text-mint"><Icon name="plus" className="h-3.5 w-3.5" /> dodaj</button>
                  </div>
                  <div className="space-y-1.5">
                    {(roz[pole] || []).map((p, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <input placeholder="rewir/opis" value={p.rewir || p.etykieta || ''} onChange={(e) => setPoz(pole, i, { rewir: e.target.value })} className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink outline-none" />
                        <input value={p.kwota} onChange={(e) => setPoz(pole, i, { kwota: e.target.value })} placeholder="kwota" className={inp} />
                        <button onClick={() => usunPoz(pole, i)} className="rounded-lg border border-danger/20 bg-danger/10 p-1.5 text-danger"><Icon name="trash" className="h-3.5 w-3.5" /></button>
                      </div>
                    ))}
                    {(roz[pole] || []).length === 0 && <p className="text-xs text-muted">Brak — dodaj wydruki.</p>}
                  </div>
                  {w && (
                    <div className="mt-2 flex items-center justify-between border-t border-line/60 pt-2 text-sm">
                      {pole === 'terminale' ? (
                        <><span className="text-muted">suma {zl(w.terminale.suma)} vs karty</span><Roznica wartosc={w.terminale.roznica_karty} etykieta={w.terminale.roznica_karty < 0 ? 'brak' : 'nadwyżka'} /></>
                      ) : (
                        <><span className="text-muted">suma {zl(w.kasy.suma)} vs deklaracje</span><Roznica wartosc={w.kasy.roznica} etykieta={w.kasy.roznica < 0 ? 'brak' : 'nadwyżka'} /></>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* IMP (imprezy −) — auto z imprez, z możliwością nadpisania z palca */}
              {w && (
                <div className="rounded-xl border border-line bg-white/[0.02] p-3">
                  <label className="flex items-center justify-between">
                    <span className="text-sm font-bold uppercase tracking-wide text-ink">IMP (imprezy −)</span>
                    <span className="flex items-center gap-1.5 text-xs text-muted">
                      <input type="checkbox" checked={!!roz.imp_reczny} onChange={(e) => toggleImpReczny(e.target.checked)} className="h-3.5 w-3.5 accent-mint" /> ręcznie
                    </span>
                  </label>
                  {roz.imp_reczny ? (
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      <label className="flex items-center gap-1.5 text-sm text-muted">gotówka sfisk.<input value={roz.imp_gotowka} onChange={(e) => setRozPole({ imp_gotowka: e.target.value })} className={inpS} /></label>
                      <label className="flex items-center gap-1.5 text-sm text-muted">karta<input value={roz.imp_karta} onChange={(e) => setRozPole({ imp_karta: e.target.value })} className={inpS} /></label>
                    </div>
                  ) : (
                    <div className="mt-2 flex items-center justify-between text-sm">
                      <span className="text-muted">auto z imprez</span>
                      <span className="font-mono text-ink">gotówka {zl(w.imp.gotowka_sfiskalizowana)} · karta {zl(w.imp.karta)}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {roz && !loading && (
        <div className="mt-5 flex flex-wrap gap-2">
          <Button onClick={() => zapisz(false)} disabled={busy}><Icon name="check" className="h-4 w-4" /> Zapisz i przelicz</Button>
          <Button variant="accent" onClick={() => zapisz(true)} disabled={busy || roz.status === 'u_szefa'}><Icon name="upload" className="h-4 w-4" /> Przekaż do szefa</Button>
        </div>
      )}
    </Card>
  )
}
