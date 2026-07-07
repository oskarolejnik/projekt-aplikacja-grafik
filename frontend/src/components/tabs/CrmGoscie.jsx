import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// CRM gości — historia rezerwacji, scoring no-show, VIP + trwały profil 360 (tagi/alergie/preferencje).
// Backend: /api/crm/goscie (lista), /api/crm/goscie/{klucz} (profil), PUT .../profil (upsert).
const RYZYKO = {
  wysokie: 'bg-danger/15 text-danger',
  srednie: 'bg-lemon/15 text-lemon',
  niskie: 'bg-white/10 text-muted',
}
const fld = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-mint'

export default function CrmGoscie() {
  const { toast } = useToast()
  const [goscie, setGoscie] = useState(null)
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)        // { klucz } — otwarty profil

  const load = useCallback(async () => {
    setLoading(true)
    try { setGoscie(await api('/crm/goscie')) }
    catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  if (loading) {
    return <Card className="p-8"><div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div></Card>
  }

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader title="Goście (CRM)" subtitle="Historia rezerwacji, ryzyko no-show, VIP i profil 360 — kliknij gościa, by edytować." />
      {!goscie || goscie.length === 0 ? (
        <div className="mt-6 rounded-xl border border-line bg-surface-2 p-8 text-center text-sm text-muted">
          Brak danych gości — pojawią się po pierwszych rezerwacjach stolików.
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-3 font-semibold">Gość</th>
                <th className="py-2 pr-3 font-semibold">Kontakt</th>
                <th className="py-2 pr-3 text-right font-semibold">Wizyt</th>
                <th className="py-2 pr-3 text-right font-semibold">No-show</th>
                <th className="py-2 pr-3 font-semibold">Ryzyko</th>
                <th className="py-2 pr-3 font-semibold">Ostatnia</th>
              </tr>
            </thead>
            <tbody>
              {goscie.map((g) => (
                <tr key={g.klucz} className="border-b border-line/60 transition hover:bg-white/[0.02]">
                  <td className="py-2.5 pr-3">
                    <button onClick={() => setModal({ klucz: g.klucz })} className="text-left font-semibold text-ink hover:text-mint">
                      {g.nazwisko || '—'}
                    </button>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {g.vip && <Pill kol="bg-mint px-2 text-bg">VIP</Pill>}
                      {g.ma_alergie && <Pill kol="bg-danger/15 text-danger"><Icon name="warning" className="mr-0.5 inline h-3 w-3" />alergie</Pill>}
                      {(g.tagi || []).map((t) => <Pill key={t} kol="bg-white/[0.06] text-muted">{t}</Pill>)}
                    </div>
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{g.telefon || g.email || '—'}</td>
                  <td className="py-2.5 pr-3 text-right text-ink tabular-nums">{g.wizyt} <span className="text-muted">({g.odbyte} odb.)</span></td>
                  <td className="py-2.5 pr-3 text-right text-ink tabular-nums">
                    {g.no_show}{g.no_show > 0 && <span className="text-muted"> ({g.no_show_proc}%)</span>}
                  </td>
                  <td className="py-2.5 pr-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${RYZYKO[g.ryzyko] || RYZYKO.niskie}`}>{g.ryzyko}</span>
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{g.ostatnia_data}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal && <ProfilModal klucz={modal.klucz} onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />}
    </Card>
  )
}

function Pill({ children, kol }) {
  return <span className={`rounded-full py-0.5 text-[10px] font-semibold ${kol.includes('px-') ? kol : `px-1.5 ${kol}`}`}>{children}</span>
}

function ProfilModal({ klucz, onClose, onSaved }) {
  const { toast } = useToast()
  const [dane, setDane] = useState(null)
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const d = await api(`/crm/goscie/${encodeURIComponent(klucz)}`)
        setDane(d)
        const p = d.profil || {}
        setForm({
          nazwisko: p.nazwisko || d.nazwisko || '', tagi: (p.tagi || []).join(', '), vip: !!p.vip,
          alergie: p.alergie || '', dieta: p.dieta || '', preferowana_strefa: p.preferowana_strefa || '',
          notatka: p.notatka || '', okazja_typ: p.okazja_typ || '', okazja_data: p.okazja_data || '',
          marketing_zgoda: !!p.marketing_zgoda,
        })
      } catch (e) { toast(e.message, 'error'); onClose() }
    })()
  }, [klucz, toast, onClose])

  const zapisz = async () => {
    setBusy(true)
    try {
      await api(`/crm/goscie/${encodeURIComponent(klucz)}/profil`, 'PUT', {
        nazwisko: form.nazwisko.trim() || null,
        tagi: form.tagi.split(',').map((s) => s.trim()).filter(Boolean),
        vip: form.vip, alergie: form.alergie.trim() || null, dieta: form.dieta.trim() || null,
        preferowana_strefa: form.preferowana_strefa.trim() || null, notatka: form.notatka.trim() || null,
        okazja_typ: form.okazja_typ || null, okazja_data: form.okazja_data.trim() || null,
        marketing_zgoda: form.marketing_zgoda,
      })
      toast('Zapisano profil gościa.', 'success'); onSaved()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const st = dane?.statystyki || {}
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="material max-h-[90dvh] w-full max-w-lg overflow-y-auto p-5 shadow-soft" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between">
          <div className="font-display text-lg font-bold text-ink">Profil gościa</div>
          <button onClick={onClose} className="text-muted hover:text-ink"><Icon name="close" className="h-5 w-5" /></button>
        </div>

        {!form ? <div className="grid place-items-center py-10"><Spinner className="h-5 w-5 text-muted" /></div> : (
          <>
            <div className="mb-4 flex flex-wrap gap-2 text-xs">
              <Metryka l="Wizyt" v={st.wizyt ?? 0} />
              <Metryka l="Odbyte" v={st.odbyte ?? 0} />
              <Metryka l="No-show" v={`${st.no_show ?? 0}${st.no_show_proc ? ` (${st.no_show_proc}%)` : ''}`} />
              {st.vip_auto && <span className="self-center rounded-full bg-mint/15 px-2 py-1 font-semibold text-mint">VIP (≥5 wizyt)</span>}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label className="col-span-2 text-xs font-semibold text-muted">Nazwisko / nazwa
                <input value={form.nazwisko} onChange={(e) => setForm((s) => ({ ...s, nazwisko: e.target.value }))} className={fld} /></label>
              <label className="col-span-2 text-xs font-semibold text-muted">Tagi (po przecinku)
                <input value={form.tagi} onChange={(e) => setForm((s) => ({ ...s, tagi: e.target.value }))} className={fld} placeholder="stały, loża, firmowy" /></label>
              <label className="col-span-2 text-xs font-semibold text-danger">Alergie / dieta specjalna · dane wrażliwe (szyfrowane)
                <input value={form.alergie} onChange={(e) => setForm((s) => ({ ...s, alergie: e.target.value }))} className={fld} placeholder="np. orzechy, gluten" /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Dieta
                <input value={form.dieta} onChange={(e) => setForm((s) => ({ ...s, dieta: e.target.value }))} className={fld} placeholder="wege / bezglutenowa" /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Preferowana strefa
                <input value={form.preferowana_strefa} onChange={(e) => setForm((s) => ({ ...s, preferowana_strefa: e.target.value }))} className={fld} placeholder="ogród / loża" /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Okazja
                <select value={form.okazja_typ} onChange={(e) => setForm((s) => ({ ...s, okazja_typ: e.target.value }))} className={fld}>
                  <option value="">—</option><option value="urodziny">Urodziny</option><option value="rocznica">Rocznica</option>
                </select></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Data okazji (MM-DD)
                <input value={form.okazja_data} onChange={(e) => setForm((s) => ({ ...s, okazja_data: e.target.value }))} className={fld} placeholder="05-12" /></label>
              <label className="col-span-2 text-xs font-semibold text-muted">Notatka (szyfrowana)
                <textarea rows={2} value={form.notatka} onChange={(e) => setForm((s) => ({ ...s, notatka: e.target.value }))} className={fld} /></label>
              <label className="col-span-1 flex items-center gap-2 text-xs font-semibold text-muted">
                <input type="checkbox" checked={form.vip} onChange={(e) => setForm((s) => ({ ...s, vip: e.target.checked }))} className="accent-mint" /> VIP (ręcznie)</label>
              <label className="col-span-1 flex items-center gap-2 text-xs font-semibold text-muted">
                <input type="checkbox" checked={form.marketing_zgoda} onChange={(e) => setForm((s) => ({ ...s, marketing_zgoda: e.target.checked }))} className="accent-mint" /> Zgoda marketingowa</label>
            </div>

            {(dane?.historia || []).length > 0 && (
              <div className="mt-4 border-t border-line pt-3">
                <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">Historia wizyt</div>
                <div className="max-h-32 space-y-1 overflow-y-auto">
                  {dane.historia.slice(0, 20).map((h, i) => (
                    <div key={i} className="flex items-center justify-between text-xs text-muted">
                      <span>{h.data}{h.godz_od ? ` · ${h.godz_od}` : ''}{h.liczba_osob ? ` · ${h.liczba_osob} os.` : ''}</span>
                      <span className="text-ink/70">{h.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-4 flex justify-end">
              <Button onClick={zapisz} disabled={busy}><Icon name="check" className="h-4 w-4" /> Zapisz profil</Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Metryka({ l, v }) {
  return (
    <span className="rounded-lg border border-line bg-surface-2 px-2.5 py-1">
      <span className="font-display font-bold tabular-nums text-ink">{v}</span> <span className="text-muted">{l}</span>
    </span>
  )
}
