import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Kalendarz imprez (admin) — siatka miesiąca. Terminy ręczne; zadatek dopasowywany z KP (osobny etap).
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const num = (v) => (v === '' || v == null ? null : parseFloat(v))
const miesiacTeraz = () => new Date().toISOString().slice(0, 7)
const DNI = ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Ndz']
const TYPY = ['wesele', 'komunia', 'chrzciny', 'stypa', 'urodziny', 'impreza firmowa', 'inne']
const STATUSY = [{ v: 'rezerwacja', l: 'Rezerwacja' }, { v: 'odbyla', l: 'Odbyła się' }, { v: 'odwolana', l: 'Odwołana' }]
const STAT_KOL = { rezerwacja: 'border-l-mint', odbyla: 'border-l-muted', odwolana: 'border-l-danger' }

const pad = (n) => String(n).padStart(2, '0')
const isoOf = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`

export default function KalendarzImprez() {
  const { toast } = useToast()
  const [mc, setMc] = useState(miesiacTeraz())
  const [terminy, setTerminy] = useState([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)   // termin (edycja) lub { data } (nowy)
  const [busy, setBusy] = useState(false)

  const [y, m] = mc.split('-').map(Number)
  const granice = () => [isoOf(y, m, 1), isoOf(y, m, new Date(y, m, 0).getDate())]

  const load = useCallback(async () => {
    setLoading(true)
    const [s, e] = [isoOf(y, m, 1), isoOf(y, m, new Date(y, m, 0).getDate())]
    try { setTerminy((await api(`/terminy?start=${s}&end=${e}`)).terminy || []) }
    catch (err) { toast(err.message, 'error') }
    finally { setLoading(false) }
  }, [y, m, toast])

  useEffect(() => { load() }, [load])

  const przesun = (delta) => {
    const d = new Date(y, m - 1 + delta, 1)
    setMc(`${d.getFullYear()}-${pad(d.getMonth() + 1)}`)
  }

  // mapowanie terminów po dacie
  const wgDnia = {}
  terminy.forEach((t) => { (wgDnia[t.data] = wgDnia[t.data] || []).push(t) })

  // komórki siatki (poniedziałek=0), 6 tygodni
  const firstWeekday = (new Date(y, m - 1, 1).getDay() + 6) % 7
  const dni = new Date(y, m, 0).getDate()
  const komorki = []
  for (let i = 0; i < 42; i++) {
    const day = i - firstWeekday + 1
    komorki.push(day >= 1 && day <= dni ? day : null)
  }
  const dzisISO = new Date().toISOString().slice(0, 10)

  const zapisz = async () => {
    if (!modal.nazwisko || !modal.nazwisko.trim()) { toast('Podaj nazwisko.', 'error'); return }
    setBusy(true)
    try {
      const body = {
        data: modal.data, nazwisko: modal.nazwisko.trim(), typ: modal.typ || null,
        liczba_osob: num(modal.liczba_osob), telefon: modal.telefon || null, sala: modal.sala || null,
        notatka: modal.notatka || null, status: modal.status || 'rezerwacja', zadatek: num(modal.zadatek) || 0,
      }
      if (modal.id) await api(`/terminy/${modal.id}`, 'PUT', body)
      else await api('/terminy', 'POST', body)
      toast('Zapisano termin.', 'success'); setModal(null); load()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const usun = async () => {
    if (!modal.id) return
    setBusy(true)
    try { await api(`/terminy/${modal.id}`, 'DELETE'); toast('Usunięto.', 'success'); setModal(null); load() }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const fld = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-mint'

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Kalendarz imprez" subtitle="Terminy imprez. Kliknij dzień, by dodać; kafelek, by edytować." />
        <div className="flex items-center gap-2">
          <button onClick={() => przesun(-1)} aria-label="Poprzedni miesiąc" className="rounded-lg border border-line px-3 py-1.5 text-lg leading-none text-muted hover:text-ink">‹</button>
          <span className="min-w-[9rem] text-center font-display text-sm font-bold text-ink">
            {new Date(y, m - 1, 1).toLocaleDateString('pl-PL', { month: 'long', year: 'numeric' })}
          </span>
          <button onClick={() => przesun(1)} aria-label="Następny miesiąc" className="rounded-lg border border-line px-3 py-1.5 text-lg leading-none text-muted hover:text-ink">›</button>
          <button onClick={() => setMc(miesiacTeraz())} className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold text-muted hover:text-ink">dziś</button>
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[680px]">
            <div className="grid grid-cols-7 gap-px border-b border-line pb-1 text-[11px] font-bold uppercase tracking-wide text-muted">
              {DNI.map((d) => <div key={d} className="px-2 py-1 text-center">{d}</div>)}
            </div>
            <div className="grid grid-cols-7 gap-px bg-line">
              {komorki.map((day, i) => {
                const iso = day ? isoOf(y, m, day) : null
                const lista = iso ? (wgDnia[iso] || []) : []
                return (
                  <div key={i} className={`min-h-[92px] bg-bg p-1.5 ${!day ? 'opacity-40' : 'cursor-pointer hover:bg-white/[0.02]'}`}
                       onClick={() => day && setModal({ data: iso, status: 'rezerwacja' })}>
                    {day && (
                      <div className={`mb-1 text-xs font-bold ${iso === dzisISO ? 'text-mint' : 'text-muted'}`}>{day}</div>
                    )}
                    <div className="space-y-1">
                      {lista.map((t) => (
                        <button key={t.id} onClick={(e) => { e.stopPropagation(); setModal(t) }}
                          className={`block w-full truncate rounded border-l-[3px] bg-surface-2 px-1.5 py-0.5 text-left text-[11px] ${STAT_KOL[t.status] || 'border-l-mint'}`}>
                          <span className="font-semibold text-ink">{t.nazwisko}</span>
                          {t.typ && <span className="text-muted"> · {t.typ}</span>}
                          {(t.zadatek || 0) > 0 && <span className="ml-1 text-mint" title="Zadatek wpłacony">●</span>}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {modal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setModal(null)}>
          <div className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-2xl border border-line bg-bg-2 p-5 shadow-glow" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-start justify-between">
              <div className="font-display text-lg font-bold text-ink">{modal.id ? 'Edytuj termin' : 'Nowy termin'}</div>
              <button onClick={() => setModal(null)} className="text-muted hover:text-ink"><Icon name="close" className="h-5 w-5" /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="col-span-1 text-xs font-semibold text-muted">Data
                <input type="date" value={modal.data} onChange={(e) => setModal((s) => ({ ...s, data: e.target.value }))} className={fld} /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Status
                <select value={modal.status || 'rezerwacja'} onChange={(e) => setModal((s) => ({ ...s, status: e.target.value }))} className={fld}>
                  {STATUSY.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
                </select></label>
              <label className="col-span-2 text-xs font-semibold text-muted">Nazwisko / klient
                <input value={modal.nazwisko || ''} onChange={(e) => setModal((s) => ({ ...s, nazwisko: e.target.value }))} className={fld} placeholder="np. Nowak" /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Typ
                <select value={modal.typ || ''} onChange={(e) => setModal((s) => ({ ...s, typ: e.target.value }))} className={fld}>
                  <option value="">—</option>{TYPY.map((t) => <option key={t} value={t}>{t}</option>)}
                </select></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Liczba osób
                <input type="number" value={modal.liczba_osob ?? ''} onChange={(e) => setModal((s) => ({ ...s, liczba_osob: e.target.value }))} className={fld} /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Telefon
                <input value={modal.telefon || ''} onChange={(e) => setModal((s) => ({ ...s, telefon: e.target.value }))} className={fld} /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Sala
                <input value={modal.sala || ''} onChange={(e) => setModal((s) => ({ ...s, sala: e.target.value }))} className={fld} /></label>
              <label className="col-span-2 text-xs font-semibold text-muted">Zadatek (zł)
                <input type="number" value={modal.zadatek ?? ''} onChange={(e) => setModal((s) => ({ ...s, zadatek: e.target.value }))} className={fld} placeholder="0,00" /></label>
              <label className="col-span-2 text-xs font-semibold text-muted">Notatka
                <textarea rows={2} value={modal.notatka || ''} onChange={(e) => setModal((s) => ({ ...s, notatka: e.target.value }))} className={fld} /></label>
            </div>
            <div className="mt-4 flex gap-2">
              <Button onClick={zapisz} disabled={busy} className="flex-1"><Icon name="check" className="h-4 w-4" /> Zapisz</Button>
              {modal.id && <button onClick={usun} disabled={busy} className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm font-semibold text-danger"><Icon name="trash" className="h-4 w-4" /></button>}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
