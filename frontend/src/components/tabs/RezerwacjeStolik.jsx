import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Zarządzanie rezerwacjami stolików (admin): lista dnia + formularz + zmiana statusu + stoliki.
// Backend: /api/rezerwacje-stolik, /api/stoliki. Moduł za flagą LokalConfig.modul_rezerwacje.

const num = (v) => (v === '' || v == null ? null : parseInt(v, 10))
const dzisISO = () => new Date().toISOString().slice(0, 10)

const STATUS_META = {
  rezerwacja:   { l: 'Rezerwacja',   kol: 'bg-lemon/15 text-lemon', akcje: [['potwierdzona', 'Potwierdź', 'check'], ['odwolana', 'Odwołaj', 'close']] },
  potwierdzona: { l: 'Potwierdzona', kol: 'bg-mint/15 text-mint',   akcje: [['odbyla', 'Odbyła', 'check'], ['no_show', 'Nie przyszli', 'warning'], ['odwolana', 'Odwołaj', 'close']] },
  odbyla:       { l: 'Odbyła',       kol: 'bg-white/10 text-muted', akcje: [] },
  no_show:      { l: 'Nie przyszli', kol: 'bg-danger/15 text-danger', akcje: [] },
  odwolana:     { l: 'Odwołana',     kol: 'bg-danger/10 text-muted', akcje: [] },
}

const fld = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-mint'

export default function RezerwacjeStolik() {
  const { toast } = useToast()
  const [data, setData] = useState(dzisISO())
  const [rez, setRez] = useState([])
  const [stoliki, setStoliki] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [modal, setModal] = useState(null)        // rezerwacja (edycja) lub { data } (nowa)
  const [stolikModal, setStolikModal] = useState(false)
  const [nowyStolik, setNowyStolik] = useState({ nazwa: '', strefa: '', pojemnosc: 2 })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [rs, ss] = await Promise.all([
        api(`/rezerwacje-stolik?start=${data}&end=${data}`),
        api('/stoliki'),
      ])
      setRez((rs.rezerwacje || []).sort((a, b) => (a.godz_od || '').localeCompare(b.godz_od || '')))
      setStoliki(ss.stoliki || [])
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [data, toast])

  useEffect(() => { load() }, [load])

  const przesun = (delta) => {
    const d = new Date(data); d.setDate(d.getDate() + delta)
    setData(d.toISOString().slice(0, 10))
  }
  const stolikNazwa = (id) => stoliki.find((s) => s.id === id)?.nazwa || '—'

  const zapisz = async () => {
    if (!modal.nazwisko || !modal.nazwisko.trim()) { toast('Podaj nazwisko / klienta.', 'error'); return }
    setBusy(true)
    try {
      const body = {
        data: modal.data, godz_od: modal.godz_od || null,
        stolik_id: modal.stolik_id ? Number(modal.stolik_id) : null,
        liczba_osob: num(modal.liczba_osob), nazwisko: modal.nazwisko.trim(),
        telefon: modal.telefon || null, email: modal.email || null,
        notatka: modal.notatka || null, zadatek: parseFloat(modal.zadatek) || 0,
      }
      if (modal.id) await api(`/rezerwacje-stolik/${modal.id}`, 'PUT', body)
      else await api('/rezerwacje-stolik', 'POST', body)
      toast('Zapisano rezerwację.', 'success'); setModal(null); load()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const usun = async () => {
    if (!modal.id) return
    setBusy(true)
    try { await api(`/rezerwacje-stolik/${modal.id}`, 'DELETE'); toast('Usunięto.', 'success'); setModal(null); load() }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const zmienStatus = async (r, nowy) => {
    try { await api(`/rezerwacje-stolik/${r.id}/status`, 'POST', { status: nowy }); load() }
    catch (e) { toast(e.message, 'error') }
  }
  const wyslijPotwierdzenie = async () => {
    try {
      const r = await api(`/rezerwacje-stolik/${modal.id}/wyslij-potwierdzenie`, 'POST')
      toast(r.wyslano ? 'E-mail potwierdzenia wysłany.' : (r.powod || 'Nie wysłano.'), r.wyslano ? 'success' : 'info')
    } catch (e) { toast(e.message, 'error') }
  }

  const dodajStolik = async () => {
    if (!nowyStolik.nazwa.trim()) { toast('Podaj nazwę stolika.', 'error'); return }
    try {
      await api('/stoliki', 'POST', { nazwa: nowyStolik.nazwa.trim(), strefa: nowyStolik.strefa || null, pojemnosc: Number(nowyStolik.pojemnosc) || 2 })
      setNowyStolik({ nazwa: '', strefa: '', pojemnosc: 2 }); load()
    } catch (e) { toast(e.message, 'error') }
  }
  const usunStolik = async (id) => {
    try { await api(`/stoliki/${id}`, 'DELETE'); load() } catch (e) { toast(e.message, 'error') }
  }

  const dataLabel = new Date(data).toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Rezerwacje stolików" subtitle="Rezerwacje na wybrany dzień. Walidacja pojemności i kolizji slotów." />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button onClick={() => setStolikModal(true)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-muted hover:text-ink">
            <Icon name="pin" className="h-3.5 w-3.5" /> Stoliki ({stoliki.length})
          </button>
          <Button onClick={() => setModal({ data, godz_od: '18:00' })} className="px-3 py-1.5 text-xs">
            <Icon name="plus" className="h-4 w-4" /> Dodaj rezerwację
          </Button>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <button onClick={() => przesun(-1)} aria-label="Poprzedni dzień" className="rounded-lg border border-line px-3 py-1.5 text-lg leading-none text-muted hover:text-ink">‹</button>
        <input type="date" value={data} onChange={(e) => setData(e.target.value)} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-mint" />
        <button onClick={() => przesun(1)} aria-label="Następny dzień" className="rounded-lg border border-line px-3 py-1.5 text-lg leading-none text-muted hover:text-ink">›</button>
        <button onClick={() => setData(dzisISO())} className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold text-muted hover:text-ink">dziś</button>
        <span className="ml-2 text-sm font-medium capitalize text-muted">{dataLabel}</span>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : rez.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line py-12 text-center text-sm text-muted">
          Brak rezerwacji na ten dzień. Kliknij „Dodaj rezerwację".
        </div>
      ) : (
        <div className="space-y-2">
          {rez.map((r) => {
            const meta = STATUS_META[r.status] || STATUS_META.rezerwacja
            return (
              <div key={r.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface-2 px-4 py-3">
                <div className="w-[88px] shrink-0 font-display text-sm font-bold tabular-nums text-ink">
                  {r.godz_od || '—'}{r.godz_do ? <span className="text-muted">–{r.godz_do}</span> : null}
                </div>
                <div className="min-w-[120px] flex-1">
                  <button onClick={() => setModal(r)} className="text-left text-sm font-semibold text-ink hover:text-mint">{r.nazwisko}</button>
                  <div className="text-xs text-muted">
                    {stolikNazwa(r.stolik_id)}{r.liczba_osob ? ` · ${r.liczba_osob} os.` : ''}{r.telefon ? ` · ${r.telefon}` : ''}
                  </div>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${meta.kol}`}>{meta.l}</span>
                <div className="flex items-center gap-1.5">
                  {meta.akcje.map(([st, label, ic]) => (
                    <button key={st} onClick={() => zmienStatus(r, st)} title={label}
                      className="rounded-lg border border-line px-2 py-1.5 text-muted transition hover:text-ink">
                      <Icon name={ic} className="h-4 w-4" />
                    </button>
                  ))}
                  <button onClick={() => setModal(r)} title="Edytuj" className="rounded-lg border border-line px-2 py-1.5 text-muted hover:text-ink">
                    <Icon name="clipboard" className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Modal rezerwacji */}
      {modal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setModal(null)}>
          <div className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-2xl border border-line bg-bg-2 p-5 shadow-glow" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-start justify-between">
              <div className="font-display text-lg font-bold text-ink">{modal.id ? 'Edytuj rezerwację' : 'Nowa rezerwacja'}</div>
              <button onClick={() => setModal(null)} className="text-muted hover:text-ink"><Icon name="close" className="h-5 w-5" /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="col-span-1 text-xs font-semibold text-muted">Data
                <input type="date" value={modal.data} onChange={(e) => setModal((s) => ({ ...s, data: e.target.value }))} className={fld} /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Godzina
                <input type="time" value={modal.godz_od || ''} onChange={(e) => setModal((s) => ({ ...s, godz_od: e.target.value }))} className={fld} /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Stolik
                <select value={modal.stolik_id || ''} onChange={(e) => setModal((s) => ({ ...s, stolik_id: e.target.value }))} className={fld}>
                  <option value="">— bez stolika —</option>
                  {stoliki.filter((s) => s.aktywny).map((s) => <option key={s.id} value={s.id}>{s.nazwa}{s.strefa ? ` (${s.strefa})` : ''} · {s.pojemnosc} os.</option>)}
                </select></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Liczba osób
                <input type="number" min="1" value={modal.liczba_osob ?? ''} onChange={(e) => setModal((s) => ({ ...s, liczba_osob: e.target.value }))} className={fld} /></label>
              <label className="col-span-2 text-xs font-semibold text-muted">Nazwisko / klient
                <input value={modal.nazwisko || ''} onChange={(e) => setModal((s) => ({ ...s, nazwisko: e.target.value }))} className={fld} placeholder="np. Nowak" /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">Telefon
                <input value={modal.telefon || ''} onChange={(e) => setModal((s) => ({ ...s, telefon: e.target.value }))} className={fld} /></label>
              <label className="col-span-1 text-xs font-semibold text-muted">E-mail
                <input value={modal.email || ''} onChange={(e) => setModal((s) => ({ ...s, email: e.target.value }))} className={fld} /></label>
              <label className="col-span-2 text-xs font-semibold text-muted">Notatka
                <textarea rows={2} value={modal.notatka || ''} onChange={(e) => setModal((s) => ({ ...s, notatka: e.target.value }))} className={fld} /></label>
            </div>
            <div className="mt-4 flex gap-2">
              <Button onClick={zapisz} disabled={busy} className="flex-1"><Icon name="check" className="h-4 w-4" /> Zapisz</Button>
              {modal.id && modal.email && (
                <button onClick={wyslijPotwierdzenie} title="Wyślij e-mail potwierdzenia"
                  className="rounded-xl border border-line px-3 py-2 text-sm font-semibold text-muted hover:text-ink"><Icon name="bell" className="h-4 w-4" /></button>
              )}
              {modal.id && <button onClick={usun} disabled={busy} className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm font-semibold text-danger"><Icon name="trash" className="h-4 w-4" /></button>}
            </div>
          </div>
        </div>
      )}

      {/* Modal stolików */}
      {stolikModal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setStolikModal(false)}>
          <div className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-2xl border border-line bg-bg-2 p-5 shadow-glow" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-start justify-between">
              <div className="font-display text-lg font-bold text-ink">Stoliki</div>
              <button onClick={() => setStolikModal(false)} className="text-muted hover:text-ink"><Icon name="close" className="h-5 w-5" /></button>
            </div>
            <div className="mb-4 space-y-1.5">
              {stoliki.length === 0 && <div className="text-sm text-muted">Brak stolików — dodaj pierwszy poniżej.</div>}
              {stoliki.map((s) => (
                <div key={s.id} className="flex items-center justify-between rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm">
                  <span className="text-ink"><span className="font-semibold">{s.nazwa}</span>{s.strefa ? <span className="text-muted"> · {s.strefa}</span> : null} <span className="text-muted">· {s.pojemnosc} os.</span></span>
                  <button onClick={() => usunStolik(s.id)} className="text-muted hover:text-danger"><Icon name="trash" className="h-4 w-4" /></button>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-6 gap-2 border-t border-line pt-3">
              <input value={nowyStolik.nazwa} onChange={(e) => setNowyStolik((s) => ({ ...s, nazwa: e.target.value }))} placeholder="Nazwa" className={`${fld} col-span-2`} />
              <input value={nowyStolik.strefa} onChange={(e) => setNowyStolik((s) => ({ ...s, strefa: e.target.value }))} placeholder="Strefa" className={`${fld} col-span-2`} />
              <input type="number" min="1" value={nowyStolik.pojemnosc} onChange={(e) => setNowyStolik((s) => ({ ...s, pojemnosc: e.target.value }))} placeholder="Os." className={`${fld} col-span-1`} />
              <button onClick={dodajStolik} className="col-span-1 grid place-items-center rounded-lg bg-accent-gradient text-bg"><Icon name="plus" className="h-4 w-4" /></button>
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
