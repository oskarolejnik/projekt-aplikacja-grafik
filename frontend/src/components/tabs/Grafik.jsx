import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { Button } from '../ui/Button'
import { WeekSelect } from '../ui/WeekSelect'
import { Banner } from '../ui/Banner'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm, zakresDni, tloKoloru } from '../../lib/format'

// Interaktywny grafik: pracownicy × dni. Status dyspozycji, przydziały zmian,
// dodawanie z szablonów wymagań, auto-przydział i czyszczenie. Logika map 1:1.
// Gęsta tabela (cały tydzień naraz); klik w komórkę otwiera modal edycji (otworzKomorke).
export default function Grafik() {
  const { stanowiska, pracownicy, week, biezacy, setWeek, reloadDicts } = useData()
  const { toast, confirm } = useToast()

  // Na wejściu w interaktywny grafik pokaż tydzień bieżący.
  useEffect(() => {
    setWeek(biezacy)
  }, [biezacy, setWeek])
  const [przydzialy, setPrzydzialy] = useState([])
  const [dyspozycje, setDyspozycje] = useState([])
  const [wymagania, setWymagania] = useState([])
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState(false)
  const [publikacja, setPublikacja] = useState({ opublikowany: false, opublikowano_at: null })
  const [publikowanie, setPublikowanie] = useState(false)
  const [dzial, setDzial] = useState('obsluga')    // który grafik: 'obsluga' | 'kuchnia'
  const [kuchniaId, setKuchniaId] = useState(null) // id ukrytego stanowiska kuchni
  const [modal, setModal] = useState(null)         // edytor komórki gęstej tabeli: { dt, p }
  const [mForm, setMForm] = useState({ stanowisko_id: '', godz_od: '', rewir: '', zamyka: false })
  const reqId = useRef(0) // chroni przed wyścigiem ładowań przy zmianie tygodnia

  const load = useCallback(async () => {
    const id = ++reqId.current
    const [s, e] = week.split('|')
    setLoading(true)
    try {
      await reloadDicts()
      const [pr, dy, wy, pub] = await Promise.all([
        api(`/przydzialy?start=${s}&end=${e}`),
        api(`/dyspozycje?start=${s}&end=${e}`),
        api(`/wymagania?start=${s}&end=${e}`),
        api(`/grafik/publikacja?start=${s}&end=${e}`),
      ])
      if (id !== reqId.current) return // starsze zapytanie (zmienił się tydzień) — pomiń
      setPrzydzialy(pr)
      setDyspozycje(dy)
      setWymagania(wy)
      setPublikacja(pub)
    } catch (err) {
      if (id === reqId.current) toast(err.message, 'error')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [week, reloadDicts, toast])

  useEffect(() => {
    load()
  }, [load])

  // Id ukrytego stanowiska kuchni (tworzone leniwie) — dla grafiku kuchni.
  useEffect(() => {
    api('/grafik/kuchnia-stanowisko').then((r) => setKuchniaId(r.id)).catch(() => {})
  }, [])

  const [s, e] = week.split('|')
  const dates = useMemo(() => zakresDni(s, e), [s, e])
  const stanMap = useMemo(() => Object.fromEntries(stanowiska.map((x) => [x.id, x])), [stanowiska])

  const przyMap = useMemo(() => {
    const m = {}
    przydzialy.forEach((a) => {
      const k = `${a.data}_${a.pracownik_id}`
      ;(m[k] = m[k] || []).push(a)
    })
    return m
  }, [przydzialy])

  const dysMap = useMemo(() => {
    const m = {}
    dyspozycje.forEach((d) => {
      m[`${d.data}_${d.pracownik_id}`] = d
    })
    return m
  }, [dyspozycje])

  const wymMap = useMemo(() => {
    const m = {}
    wymagania.forEach((w) => {
      ;(m[w.data] = m[w.data] || []).push(w)
    })
    return m
  }, [wymagania])

  // Szablony (wymagania) dostępne dla danego pracownika w danym dniu.
  const szablonyDla = useCallback(
    (dt, p) => {
      const isW = [0, 6].includes(new Date(dt).getDay())
      const kwalIds = new Set((p.kwalifikacje || []).map((k) => k.id))
      return (wymMap[dt] || []).filter((w) => {
        const stan = stanMap[w.stanowisko_id]
        return stan && (!stan.tylko_weekend || isW) && kwalIds.has(w.stanowisko_id)
      })
    },
    [wymMap, stanMap],
  )

  const autoAssign = async () => {
    setProcessing(true)
    try {
      await api(`/auto-assign?start=${s}&end=${e}`, 'POST')
      await load()
      // Auto-przydział TYLKO szkicuje: backend cofa publikację, więc obsługa nie widzi zmian,
      // dopóki nie klikniesz „Udostępnij pracownikom".
      toast('Auto-przydział gotowy — grafik jest szkicem. Sprawdź i opublikuj.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setProcessing(false)
    }
  }
  const wyczysc = async () => {
    const ktory = jestKuchnia ? 'kuchni' : 'obsługi'
    if (!(await confirm(`Wyczyścić grafik ${ktory} na ten tydzień? Drugi grafik (${jestKuchnia ? 'obsługi' : 'kuchni'}) zostaje nietknięty.`, { title: 'Wyczyść tabelę', confirmText: 'Wyczyść' }))) return
    try {
      await api(`/przydzialy?start=${s}&end=${e}&dzial=${jestKuchnia ? 'kuchnia' : 'obsluga'}`, 'DELETE')
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const udostepnij = async (cisza = false) => {
    setPublikowanie(true)
    try {
      const r = await api(`/grafik/publikuj?start=${s}&end=${e}${cisza ? '&cisza=true' : ''}`, 'POST')
      setPublikacja({ opublikowany: true, opublikowano_at: r.opublikowano_at })
      toast(
        cisza
          ? 'Grafik opublikowany po cichu (bez powiadomień).'
          : `Grafik udostępniony pracownikom${r.push_wyslano ? ` (powiadomienia: ${r.push_wyslano})` : ''}.`,
        'success',
      )
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setPublikowanie(false)
    }
  }

  const cofnijPublikacje = async () => {
    if (!(await confirm('Cofnąć publikację grafiku na ten tydzień? Pracownicy przestaną go widzieć.', { title: 'Cofnij publikację', confirmText: 'Cofnij publikację' }))) return
    setPublikowanie(true)
    try {
      await api(`/grafik/publikuj?start=${s}&end=${e}`, 'DELETE')
      setPublikacja({ opublikowany: false, opublikowano_at: null })
      toast('Publikacja cofnięta — grafik ukryty przed pracownikami.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setPublikowanie(false)
    }
  }

  // Osobne grafiki: pokazujemy tylko pracowników wybranego działu.
  const aktywni = pracownicy.filter((p) => p.aktywny && (p.dzial || 'obsluga') === dzial)
  const jestKuchnia = dzial === 'kuchnia'

  const dayLabel = (dt) => {
    const [, mm, dd] = dt.split('-')
    return { wd: new Date(dt).toLocaleDateString('pl-PL', { weekday: 'short' }).replace('.', ''), dm: `${dd}.${mm}` }
  }
  const cellBgFor = (dt, p) => {
    const dys = dysMap[`${dt}_${p.id}`]
    // Mocniejsze tło zielone/czerwone — żeby pole „od razu" pokazywało dostępność.
    return !dys ? 'bg-white/[0.01]' : dys.dostepnosc ? 'bg-success/[0.14]' : 'bg-danger/[0.14]'
  }

  // ── Edytor komórki (gęsta tabela): klik w pole otwiera modal (dodawanie lub edycja) ──
  const otworzKomorke = (dt, p) => {
    const a = (przyMap[`${dt}_${p.id}`] || [])[0]
    if (a) {
      setMForm({ stanowisko_id: String(a.stanowisko_id), godz_od: a.godz_od ? hhmm(a.godz_od) : '', rewir: a.rewir || '', zamyka: !!a.zamyka })
    } else {
      const szab = szablonyDla(dt, p)[0]   // podpowiedź z planu (wymagania)
      setMForm({
        stanowisko_id: jestKuchnia ? String(kuchniaId ?? '') : (szab ? String(szab.stanowisko_id) : ''),
        godz_od: szab?.godz_od ? hhmm(szab.godz_od) : '',
        rewir: szab?.rewir || '',
        zamyka: false,
      })
    }
    setModal({ dt, p })
  }

  const zapiszModal = async () => {
    const { dt, p } = modal
    const a = (przyMap[`${dt}_${p.id}`] || [])[0]
    const sid = +mForm.stanowisko_id || (jestKuchnia ? kuchniaId : 0)
    if (!sid) { toast('Wybierz stanowisko.', 'error'); return }
    const body = { data: dt, stanowisko_id: sid, pracownik_id: p.id, godz_od: mForm.godz_od ? `${mForm.godz_od}:00` : null, rewir: (mForm.rewir || '').trim() || null }
    try {
      let aid = a?.id
      if (a) await api(`/przydzialy/${a.id}`, 'PUT', body)
      else { const nowy = await api('/przydzialy', 'POST', body); aid = nowy.id }
      // „Zamyka lokal" ręcznie — wysyłamy tylko gdy zmienione względem stanu (obsługa).
      if (!jestKuchnia && aid != null && !!mForm.zamyka !== !!(a && a.zamyka)) {
        await api(`/przydzialy/${aid}/zamyka`, 'PUT', { reczny: !!mForm.zamyka })
      }
      setModal(null); load()
    } catch (err) { toast(err.message, 'error') }
  }

  const usunModal = async () => {
    const { dt, p } = modal
    const a = (przyMap[`${dt}_${p.id}`] || [])[0]
    if (!a) { setModal(null); return }
    try { await api(`/przydzialy/${a.id}`, 'DELETE'); setModal(null); load() } catch (err) { toast(err.message, 'error') }
  }

  return (
    <div className="space-y-6">
      {/* Osobne grafiki: obsługa / kuchnia (filtr widoku — publikacja i tak obejmuje cały tydzień) */}
      <div className="flex gap-2">
        {[['obsluga', 'Grafik obsługa'], ['kuchnia', 'Grafik kuchnia']].map(([v, label]) => (
          <button
            key={v}
            onClick={() => { setDzial(v); setModal(null) }}
            className={`rounded-xl px-4 py-2 text-sm font-bold transition active:scale-[0.97] ${
              dzial === v ? 'bg-accent-gradient text-bg shadow-glow' : 'border border-line bg-white/[0.03] text-muted hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <WeekSelect />
        <div className="flex flex-wrap items-center gap-3">
          {!jestKuchnia && (
            <Button variant="success" onClick={autoAssign} disabled={processing}>
              {processing ? <Spinner className="h-4 w-4" /> : <Icon name="robot" className="h-5 w-5" />}
              Auto-przydział AI
            </Button>
          )}
          <Button variant="ghost" onClick={wyczysc} className="text-danger hover:bg-danger/10">
            Wyczyść tabelę
          </Button>
          <Button onClick={() => udostepnij(false)} disabled={publikowanie}>
            {publikowanie ? <Spinner className="h-4 w-4" /> : <Icon name="bell" className="h-4 w-4" />}
            {publikacja.opublikowany ? 'Udostępnij ponownie' : 'Udostępnij pracownikom'}
          </Button>
          <Button
            variant="ghost"
            onClick={() => udostepnij(true)}
            disabled={publikowanie}
            title="Publikuje bez wysyłania powiadomień push (np. dla starych tygodni)"
          >
            Po cichu
          </Button>
          {publikacja.opublikowany && (
            <Button variant="ghost" onClick={cofnijPublikacje} disabled={publikowanie} className="text-danger hover:bg-danger/10">
              Cofnij publikację
            </Button>
          )}
          <span className={`text-xs font-semibold ${publikacja.opublikowany ? 'text-success' : 'text-muted'}`}>
            {publikacja.opublikowany
              ? `Opublikowano: ${new Date(publikacja.opublikowano_at).toLocaleString('pl-PL')}`
              : 'Nieopublikowane'}
          </span>
        </div>
      </div>

      {processing && <Banner variant="info">Trwa procesowanie algorytmu auto-przydziału…</Banner>}

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : aktywni.length === 0 ? (
        <Banner variant="info">
          {jestKuchnia ? 'Brak pracowników w dziale kuchnia — ustaw dział w zakładce „Pracownicy".' : 'Brak aktywnych pracowników.'}
        </Banner>
      ) : (
        <>
          <p className="mb-2 text-xs text-muted">Cały tydzień na raz. Kliknij pole, aby dodać lub zmienić zmianę. Tło: <span className="font-bold text-success">zielone</span> = dostępny (✓), <span className="font-bold text-danger">czerwone</span> = nie (✗). 🔑 = zamyka lokal.</p>
          <div className="card overflow-auto p-0" style={{ maxHeight: '74vh' }}>
            <table className="w-full border-separate border-spacing-0">
              <thead>
                <tr>
                  <th className="sticky left-0 top-0 z-30 min-w-[104px] border-b border-r border-line bg-surface-2 p-2 text-left text-[10px] font-bold uppercase tracking-wider text-muted">
                    Pracownik
                  </th>
                  {dates.map((dt) => {
                    const { wd, dm } = dayLabel(dt)
                    const isW = [0, 6].includes(new Date(dt).getDay())
                    return (
                      <th key={dt} className={`sticky top-0 z-20 min-w-[60px] border-b border-r border-line bg-surface-2 p-1.5 text-center text-xs font-bold ${isW ? 'text-blush' : 'text-ink'}`}>
                        <div className="text-[9px] uppercase tracking-wide opacity-60">{wd}</div>
                        {dm}
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {aktywni.map((p) => (
                  <tr key={p.id}>
                    <td className="sticky left-0 z-10 min-w-[104px] border-b border-r border-line p-2 text-[11px] font-semibold leading-tight text-ink shadow-[2px_0_8px_rgba(0,0,0,0.3)]" style={{ background: tloKoloru(p.kolor) }}>
                      {p.imie} {p.nazwisko}
                    </td>
                    {dates.map((dt) => {
                      const a = (przyMap[`${dt}_${p.id}`] || [])[0]
                      const dys = dysMap[`${dt}_${p.id}`]
                      return (
                        <td
                          key={dt}
                          onClick={() => otworzKomorke(dt, p)}
                          title="Kliknij, aby dodać / zmienić"
                          className={`relative cursor-pointer border-b border-r border-line p-0.5 text-center align-middle transition hover:brightness-150 ${cellBgFor(dt, p)}`}
                        >
                          {dys && (
                            <span
                              className={`absolute left-0.5 top-0.5 ${dys.dostepnosc ? 'text-success' : 'text-danger'}`}
                              title={dys.dostepnosc ? (dys.godz_od ? `Dostępny od ${hhmm(dys.godz_od)}` : 'Dostępny') : 'Niedostępny'}
                            >
                              <Icon name={dys.dostepnosc ? 'check' : 'close'} className="h-2.5 w-2.5" strokeWidth={3} />
                            </span>
                          )}
                          {a ? (
                            <div className="px-0.5 py-1.5">
                              <div className="text-[10px] font-bold leading-tight text-ink">{stanMap[a.stanowisko_id]?.nazwa || '?'}</div>
                              <div className="font-mono text-[10px] leading-tight text-muted">{a.godz_od ? hhmm(a.godz_od) : '—'}</div>
                              {!jestKuchnia && a.zamyka && (
                                <span title={`zamyka lokal${a.zamyka_reczny ? ' (ręcznie)' : ''}`} className="mt-0.5 inline-flex text-lemon"><Icon name="key" className="h-2.5 w-2.5" /></span>
                              )}
                            </div>
                          ) : (
                            <span className="text-base font-bold text-muted/25">+</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {modal && (() => {
        const a = (przyMap[`${modal.dt}_${modal.p.id}`] || [])[0]
        const dys = dysMap[`${modal.dt}_${modal.p.id}`]
        const { wd, dm } = dayLabel(modal.dt)
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={() => setModal(null)}>
            <div className="w-full max-w-sm rounded-2xl border border-line bg-bg-2 p-5 shadow-2xl" onClick={(ev) => ev.stopPropagation()}>
              <div className="mb-3 flex items-start justify-between">
                <div>
                  <div className="font-display text-lg font-bold text-ink">{modal.p.imie} {modal.p.nazwisko}</div>
                  <div className="text-xs capitalize text-muted">{wd} {dm}</div>
                </div>
                <button onClick={() => setModal(null)} className="text-muted transition hover:text-ink" aria-label="Zamknij"><Icon name="close" className="h-5 w-5" /></button>
              </div>
              {!jestKuchnia && (
                <div className={`mb-3 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-bold ${!dys ? 'bg-white/[0.06] text-muted' : dys.dostepnosc ? 'bg-success text-bg' : 'bg-danger text-white'}`}>
                  {!dys ? '? brak zgłoszonej dostępności' : dys.dostepnosc ? <><Icon name="check" className="h-3.5 w-3.5" strokeWidth={3} /> Dostępny{dys.godz_od ? ` od ${hhmm(dys.godz_od)}` : ''}</> : <><Icon name="close" className="h-3.5 w-3.5" strokeWidth={3} /> Niedostępny</>}
                </div>
              )}
              <div className="flex flex-col gap-2">
                <select value={mForm.stanowisko_id} onChange={(ev) => setMForm((f) => ({ ...f, stanowisko_id: ev.target.value }))} className="w-full cursor-pointer rounded-md border border-line bg-surface p-2 text-sm text-ink outline-none">
                  {!jestKuchnia && <option value="">— stanowisko —</option>}
                  {(jestKuchnia ? stanowiska : stanowiska.filter((st) => st.id !== kuchniaId)).map((st) => <option key={st.id} value={st.id}>{st.nazwa}</option>)}
                </select>
                <input type="time" value={mForm.godz_od} onChange={(ev) => setMForm((f) => ({ ...f, godz_od: ev.target.value }))} className="w-full rounded-md border border-line bg-surface p-2 text-sm text-ink outline-none" />
                {!jestKuchnia && <input value={mForm.rewir} onChange={(ev) => setMForm((f) => ({ ...f, rewir: ev.target.value }))} placeholder="rewir (opcjonalnie)" className="w-full rounded-md border border-line bg-surface p-2 text-sm text-ink outline-none" />}
                {!jestKuchnia && (
                  <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
                    <input type="checkbox" checked={mForm.zamyka} onChange={(ev) => setMForm((f) => ({ ...f, zamyka: ev.target.checked }))} className="h-4 w-4 accent-lemon" />
                    Zamyka lokal <span className="text-[11px] text-muted">(domyślnie automat — najpóźniejszy z Sali)</span>
                  </label>
                )}
              </div>
              <div className="mt-4 flex items-center gap-2">
                <button onClick={zapiszModal} className="flex-1 rounded-xl bg-cream py-2.5 text-sm font-bold uppercase tracking-[0.15em] text-bg transition hover:brightness-[1.03] active:scale-[0.98]">Zapisz</button>
                {a && <button onClick={usunModal} className="rounded-xl border border-danger/40 px-4 py-2.5 text-sm font-bold text-danger transition hover:bg-danger/10">Usuń</button>}
              </div>
            </div>
          </div>
        )
      })()}
    </div>
  )
}
