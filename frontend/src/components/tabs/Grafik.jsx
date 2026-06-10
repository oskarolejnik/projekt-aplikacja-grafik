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
import { motion } from 'framer-motion'
import { SPRING_PILL } from '../../lib/motion'

// Interaktywny grafik: pracownicy × dni. Status dyspozycji, przydziały zmian,
// dodawanie z szablonów wymagań, auto-przydział i czyszczenie. Logika map 1:1.
// Prezentacja responsywna: desktop = macierz (tabela), mobile = wybór dnia + lista
// pracowników. Render pojedynczej komórki wydzielony do komorka(dt, p) — wspólny dla obu.
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
  const [selDay, setSelDay] = useState('') // wybrany dzień w widoku mobilnym
  const [reczny, setReczny] = useState(null) // ręczne przypisanie: { key, stanowisko_id, godz_od, rewir, zamyka }
  const [edycja, setEdycja] = useState(null) // edycja istniejącego przydziału: { id, rewir, zamyka }
  const [dzial, setDzial] = useState('obsluga')    // który grafik: 'obsluga' | 'kuchnia'
  const [kuchniaId, setKuchniaId] = useState(null) // id ukrytego stanowiska kuchni
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

  const dodajPrzydzial = async (dt, pId, w) => {
    try {
      await api('/przydzialy', 'POST', { data: dt, stanowisko_id: w.stanowisko_id, pracownik_id: pId, godz_od: w.godz_od, rewir: w.rewir })
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }
  // Wolne przypisanie: dowolne stanowisko + własna godzina, niezależnie od dyspozycyjności/wymagań.
  const dodajRecznie = async (dt, pId) => {
    // W grafiku kuchni domyślne stanowisko = Kuchnia, ale można wybrać inne (np. Techniczny) na tę zmianę.
    const kuchnia = dzial === 'kuchnia'
    const stanowisko_id = kuchnia ? (+reczny.stanowisko_id || kuchniaId) : +reczny.stanowisko_id
    if (!stanowisko_id) {
      toast(kuchnia ? 'Brak stanowiska kuchni — odśwież stronę.' : 'Wybierz stanowisko.', 'error')
      return
    }
    try {
      await api('/przydzialy', 'POST', {
        data: dt,
        stanowisko_id,
        pracownik_id: pId,
        godz_od: reczny.godz_od ? `${reczny.godz_od}:00` : null,
        rewir: (reczny.rewir || '').trim() || null,
        zamyka: !!reczny.zamyka,
      })
      setReczny(null)
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  // Edycja istniejącego przydziału: rewir + „zamyka" (PUT zachowuje resztę).
  const zapiszEdycje = async (a) => {
    try {
      await api(`/przydzialy/${a.id}`, 'PUT', {
        data: a.data,
        stanowisko_id: a.stanowisko_id,
        pracownik_id: a.pracownik_id,
        godz_od: a.godz_od,
        rewir: (edycja.rewir || '').trim() || null,
        zamyka: !!edycja.zamyka,
      })
      setEdycja(null)
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const usunPrzydzial = async (aid) => {
    try {
      await api(`/przydzialy/${aid}`, 'DELETE')
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const autoAssign = async () => {
    setProcessing(true)
    try {
      await api(`/auto-assign?start=${s}&end=${e}`, 'POST')
      await load()
      toast('Auto-przydział zakończony.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setProcessing(false)
    }
  }
  const wyczysc = async () => {
    if (!(await confirm('Wyczyścić cały grafik dla tego tygodnia?'))) return
    try {
      await api(`/przydzialy?start=${s}&end=${e}`, 'DELETE')
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
  const selectedDay = dates.includes(selDay) ? selDay : dates[0]

  const dayLabel = (dt) => {
    const [, mm, dd] = dt.split('-')
    return { wd: new Date(dt).toLocaleDateString('pl-PL', { weekday: 'short' }).replace('.', ''), dm: `${dd}.${mm}` }
  }
  const cellBgFor = (dt, p) => {
    const dys = dysMap[`${dt}_${p.id}`]
    return !dys ? 'bg-white/[0.01]' : dys.dostepnosc ? 'bg-success/[0.04]' : 'bg-danger/[0.04]'
  }

  // Render zawartości jednej komórki (status + przydziały + dodawanie). Wspólny dla
  // tabeli (desktop) i kart dnia (mobile).
  const komorka = (dt, p) => {
    const key = `${dt}_${p.id}`
    const dys = dysMap[key]
    const pAt = przyMap[key] || []
    const szablony = szablonyDla(dt, p)
    const status = dys ? (dys.dostepnosc ? (dys.godz_od ? `Od ${hhmm(dys.godz_od)}` : 'Dostępny') : 'Niedostępny') : 'brak'
    const statusColor = !dys
      ? 'text-muted border-line'
      : dys.dostepnosc
        ? 'text-success border-success/30 bg-success/10'
        : 'text-danger border-danger/30 bg-danger/10'

    return (
      <>
        {!jestKuchnia && <div className={`mb-2 w-fit rounded-md border px-2 py-0.5 text-[10px] font-bold ${statusColor}`}>{status}</div>}
        <div className="flex flex-col gap-2">
          {pAt.map((a) => {
            const stan = stanMap[a.stanowisko_id]
            const szab = szablony.find((w) => w.stanowisko_id === a.stanowisko_id && w.godz_od === a.godz_od)
            const edytuje = edycja?.id === a.id
            return (
              <div key={a.id} className={`rounded-lg border border-line border-l-[3px] bg-surface-2 p-2 text-left text-xs ${(!jestKuchnia && a.zamyka) ? 'border-l-lemon' : 'border-l-mint'}`}>
                <div className="flex items-start justify-between gap-1">
                  <span className="font-bold text-ink">
                    {stan?.nazwa}
                    {!jestKuchnia && (a.rewir || szab?.rewir) && <span className="text-mint"> ({a.rewir || szab?.rewir})</span>}
                  </span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {!jestKuchnia && a.zamyka && <span title="zamyka lokal" className="text-lemon"><Icon name="key" className="h-3 w-3" /></span>}
                    {!jestKuchnia && (
                      <button onClick={() => setEdycja(edytuje ? null : { id: a.id, rewir: a.rewir || '', zamyka: !!a.zamyka })} className="text-[10px] font-semibold text-muted transition hover:text-mint">
                        {edytuje ? 'anuluj' : 'edytuj'}
                      </button>
                    )}
                    <button onClick={() => usunPrzydzial(a.id)} className="text-muted transition hover:text-danger" aria-label="Anuluj zmianę">
                      <Icon name="close" className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <span className="mt-1 flex items-center gap-1.5 font-mono text-[10px] text-muted">
                  <Icon name="clock" className="h-3 w-3" /> {a.godz_od ? hhmm(a.godz_od) : 'Dowolnie'}
                  {!jestKuchnia && a.zamyka && <span className="font-sans font-bold text-lemon">· zamyka</span>}
                </span>
                {edytuje && (
                  <div className="mt-1.5 flex flex-col gap-1.5 border-t border-line pt-1.5">
                    <input
                      value={edycja.rewir}
                      onChange={(ev) => setEdycja((x) => ({ ...x, rewir: ev.target.value }))}
                      placeholder="rewir (np. Parter)"
                      className="w-full rounded-md border border-line bg-surface p-1.5 text-xs text-ink outline-none"
                    />
                    <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ink">
                      <input type="checkbox" checked={edycja.zamyka} onChange={(ev) => setEdycja((x) => ({ ...x, zamyka: ev.target.checked }))} className="h-3.5 w-3.5 accent-lemon" />
                      Zamyka lokal
                    </label>
                    <button onClick={() => zapiszEdycje(a)} className="rounded-md bg-mint/20 py-1 text-xs font-bold text-mint transition hover:bg-mint/30">Zapisz</button>
                  </div>
                )}
              </div>
            )
          })}

          {/* Maks. 1 zmiana/dzień — opcje dodawania znikają, gdy pracownik ma już przydział. */}
          {pAt.length === 0 && (
            <>
              {dys?.dostepnosc && szablony.length > 0 && (
                <select
                  value=""
                  onChange={(ev) => {
                    const idx = ev.target.value
                    if (idx === '') return
                    dodajPrzydzial(dt, p.id, szablony[+idx])
                  }}
                  className="w-full cursor-pointer rounded-lg border border-dashed border-line bg-surface-2 p-1.5 text-center text-xs font-medium text-mint outline-none transition hover:border-mint/50"
                >
                  <option value="" className="bg-surface text-muted">+ Dodaj (wg planu)</option>
                  {szablony.map((w, i) => (
                    <option key={i} value={i} className="bg-surface text-ink">
                      {stanMap[w.stanowisko_id].nazwa}
                      {w.rewir ? ` (${w.rewir})` : ''}
                      {w.godz_od ? ` [${hhmm(w.godz_od)}]` : ''}
                    </option>
                  ))}
                </select>
              )}

              {reczny?.key === key ? (
                <div className="flex flex-col gap-1.5 rounded-lg border border-dashed border-mint/40 bg-surface-2 p-2">
                  {!jestKuchnia && !dys?.dostepnosc && <span className="text-[10px] font-bold text-lemon">⚠ Pracownik nie zgłosił dostępności</span>}
                  <select
                    value={reczny.stanowisko_id}
                    onChange={(ev) => setReczny((r) => ({ ...r, stanowisko_id: ev.target.value }))}
                    className="w-full cursor-pointer rounded-md border border-line bg-surface p-1.5 text-xs text-ink outline-none"
                  >
                    {!jestKuchnia && <option value="">— stanowisko —</option>}
                    {(jestKuchnia ? stanowiska : stanowiska.filter((st) => st.id !== kuchniaId)).map((st) => (
                      <option key={st.id} value={st.id}>{st.nazwa}</option>
                    ))}
                  </select>
                  <input
                    type="time"
                    value={reczny.godz_od}
                    onChange={(ev) => setReczny((r) => ({ ...r, godz_od: ev.target.value }))}
                    className="w-full rounded-md border border-line bg-surface p-1.5 text-xs text-ink outline-none"
                  />
                  {!jestKuchnia && (
                    <>
                      <input
                        value={reczny.rewir}
                        onChange={(ev) => setReczny((r) => ({ ...r, rewir: ev.target.value }))}
                        placeholder="rewir (opcjonalnie)"
                        className="w-full rounded-md border border-line bg-surface p-1.5 text-xs text-ink outline-none"
                      />
                      <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ink">
                        <input type="checkbox" checked={reczny.zamyka} onChange={(ev) => setReczny((r) => ({ ...r, zamyka: ev.target.checked }))} className="h-3.5 w-3.5 accent-lemon" />
                        Zamyka lokal
                      </label>
                    </>
                  )}
                  <div className="flex gap-1.5">
                    <button onClick={() => dodajRecznie(dt, p.id)} className="flex-1 rounded-md bg-mint/20 py-1 text-xs font-bold text-mint transition hover:bg-mint/30">Dodaj</button>
                    <button onClick={() => setReczny(null)} className="rounded-md border border-line px-2 py-1 text-xs text-muted transition hover:text-ink">Anuluj</button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setReczny({ key, stanowisko_id: jestKuchnia ? String(kuchniaId ?? '') : '', godz_od: '', rewir: '', zamyka: false })}
                  className="w-full rounded-lg border border-dashed border-line bg-surface-2 p-1.5 text-center text-xs font-medium text-muted outline-none transition hover:border-mint/50 hover:text-mint"
                >
                  + ręcznie
                </button>
              )}
            </>
          )}
        </div>
      </>
    )
  }

  return (
    <div className="space-y-6">
      {/* Osobne grafiki: obsługa / kuchnia (filtr widoku — publikacja i tak obejmuje cały tydzień) */}
      <div className="flex gap-2">
        {[['obsluga', 'Grafik obsługa'], ['kuchnia', 'Grafik kuchnia']].map(([v, label]) => (
          <button
            key={v}
            onClick={() => { setDzial(v); setReczny(null); setEdycja(null) }}
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
          {/* MOBILE / wąskie ekrany: wybór dnia + lista pracowników na ten dzień */}
          <div className="lg:hidden">
            <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
              {dates.map((dt) => {
                const { wd, dm } = dayLabel(dt)
                const isW = [0, 6].includes(new Date(dt).getDay())
                const sel = dt === selectedDay
                return (
                  <button
                    key={dt}
                    onClick={() => setSelDay(dt)}
                    className="relative flex shrink-0 flex-col items-center rounded-xl border border-line bg-white/[0.03] px-3.5 py-2 transition-transform active:scale-[0.95]"
                    style={{ WebkitTapHighlightColor: 'transparent' }}
                  >
                    {sel && (
                      <motion.span layoutId="grafikDay" transition={SPRING_PILL} className="absolute inset-0 rounded-xl bg-accent-gradient shadow-glow" />
                    )}
                    <span className={`relative z-10 text-[10px] font-bold uppercase tracking-wide ${sel ? 'text-bg' : isW ? 'text-blush' : 'text-muted'}`}>{wd}</span>
                    <span className={`relative z-10 text-sm font-bold ${sel ? 'text-bg' : isW ? 'text-blush' : 'text-ink'}`}>{dm}</span>
                  </button>
                )
              })}
            </div>
            <div className="space-y-3">
              {aktywni.map((p, i) => (
                <div
                  key={p.id}
                  className="animate-fade-up rounded-xl border border-line bg-white/[0.02] p-4"
                  style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
                >
                  <div className="mb-2.5 rounded-lg px-2 py-1 text-sm font-semibold text-ink" style={{ background: tloKoloru(p.kolor) }}>
                    {p.imie} {p.nazwisko}
                  </div>
                  {komorka(selectedDay, p)}
                </div>
              ))}
            </div>
          </div>

          {/* DESKTOP: pełna macierz pracownicy × dni (mniejsze nazwy) */}
          <div className="hidden lg:block">
            <div className="card overflow-x-auto p-0">
              <table className="w-full border-separate border-spacing-0">
                <thead>
                  <tr>
                    <th className="sticky left-0 z-20 min-w-[120px] border-b border-r border-line bg-surface-2 p-3 text-left text-[11px] font-bold uppercase tracking-wider text-muted">
                      Pracownik
                    </th>
                    {dates.map((dt) => {
                      const [, mm, dd] = dt.split('-')
                      const isW = [0, 6].includes(new Date(dt).getDay())
                      return (
                        <th
                          key={dt}
                          className={`min-w-[140px] border-b border-r border-line p-3 text-center text-sm font-bold ${isW ? 'text-blush' : 'text-ink'}`}
                        >
                          {dd}.{mm}
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {aktywni.map((p) => (
                    <tr key={p.id}>
                      <td className="sticky left-0 z-10 border-b border-r border-line bg-bg-2 p-3 text-xs font-semibold text-ink shadow-[2px_0_8px_rgba(0,0,0,0.25)]" style={{ background: tloKoloru(p.kolor) }}>
                        {p.imie} {p.nazwisko}
                      </td>
                      {dates.map((dt) => (
                        <td key={dt} className={`border-b border-r border-line p-2.5 align-top ${cellBgFor(dt, p)}`}>
                          {komorka(dt, p)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
