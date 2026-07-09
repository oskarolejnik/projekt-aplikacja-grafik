import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { Card, SectionHeader } from '../components/ui/Card'
import { WeekSelect } from '../components/ui/WeekSelect'
import { Banner } from '../components/ui/Banner'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useData } from '../context/DataContext'
import { useToast } from '../components/ui/Toast'
import { hhmm, zakresDni, tloKoloru } from '../lib/format'

// Edytowalny grafik kuchni dla SZEFA KUCHNI — korekty na żywo. Każda zmiana od razu
// trafia do kucharza (grafik kuchni jest „żywy") i wysyła powiadomienie. Dane i zapisy
// przez /api/szefkuchni/* (osobna przestrzeń uprawnień — bez publikacji/AI/obsługi).
export default function SzefKuchniGrafik() {
  const { week, biezacy, setWeek } = useData()
  const { toast, confirm } = useToast()
  const [pracownicy, setPracownicy] = useState([])
  const [przydzialy, setPrzydzialy] = useState([])
  const [naZmianie, setNaZmianie] = useState([])
  const [loading, setLoading] = useState(true)
  const [selDay, setSelDay] = useState('')
  const [dodaj, setDodaj] = useState(null)   // { pracownik_id, godz_od, rewir, zamyka }
  const [edycja, setEdycja] = useState(null) // { id, godz_od, rewir, zamyka }
  const reqId = useRef(0)

  useEffect(() => { setWeek(biezacy) }, [biezacy, setWeek])
  const [s, e] = week.split('|')

  const load = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    try {
      const r = await api(`/szefkuchni/grafik?start=${s}&end=${e}`)
      if (id !== reqId.current) return
      setPracownicy(r.pracownicy || [])
      setPrzydzialy(r.przydzialy || [])
      setNaZmianie(r.na_zmianie || [])
    } catch (err) {
      if (id === reqId.current) toast(err.message, 'error')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [s, e, toast])
  useEffect(() => { load() }, [load])

  const dates = useMemo(() => zakresDni(s, e), [s, e])
  const selectedDay = dates.includes(selDay) ? selDay : dates[0]
  const przyMap = useMemo(() => {
    const m = {}
    przydzialy.forEach((a) => {
      const k = `${a.data}_${a.pracownik_id}`
      ;(m[k] = m[k] || []).push(a)
    })
    return m
  }, [przydzialy])

  const aktywni = pracownicy.filter((p) => p.aktywny)

  const dodajZmiane = async (pid) => {
    try {
      await api('/szefkuchni/przydzialy', 'POST', {
        data: selectedDay, stanowisko_id: 0, pracownik_id: pid,
        godz_od: dodaj.godz_od ? `${dodaj.godz_od}:00` : null,
        rewir: null, zamyka: false,  // kuchnia: bez rewiru i bez „zamyka lokal"
      })
      setDodaj(null); load()
    } catch (err) { toast(err.message, 'error') }
  }
  const zapiszEdycje = async (a) => {
    try {
      await api(`/szefkuchni/przydzialy/${a.id}`, 'PUT', {
        data: a.data, stanowisko_id: 0, pracownik_id: a.pracownik_id,
        godz_od: edycja.godz_od ? `${edycja.godz_od}:00` : null,
        rewir: null, zamyka: false,  // kuchnia: bez rewiru i bez „zamyka lokal"
      })
      setEdycja(null); load()
    } catch (err) { toast(err.message, 'error') }
  }
  const usun = async (a) => {
    if (!(await confirm('Wykreślić tę zmianę z grafiku kuchni? Kucharz dostanie powiadomienie.'))) return
    try { await api(`/szefkuchni/przydzialy/${a.id}`, 'DELETE'); load() } catch (err) { toast(err.message, 'error') }
  }

  const dayLabel = (dt) => {
    const [, mm, dd] = dt.split('-')
    return { wd: new Date(dt).toLocaleDateString('pl-PL', { weekday: 'short' }).replace('.', ''), dm: `${dd}.${mm}` }
  }

  return (
    <Card className="p-6 md:p-8">
      <SectionHeader title="Grafik kuchni" subtitle="Korekty na żywo — każda zmiana od razu trafia do kucharza (z powiadomieniem).">
        <WeekSelect />
      </SectionHeader>

      {/* Kto z kuchni jest teraz na zmianie (live z RCP) — od razu na głównej zakładce */}
      {naZmianie.length > 0 && (
        <div className="mb-4 rounded-xl border border-mint/30 bg-mint/[0.05] p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-mint" />
            </span>
            <span className="text-sm font-bold text-ink">Kuchnia na zmianie teraz ({naZmianie.length})</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {naZmianie.map((z, i) => (
              <span key={i} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white/[0.03] px-2.5 py-1 text-xs">
                <span className="font-semibold text-ink">{z.pracownik}</span>
                <span className="font-mono text-muted">od {z.wejscie.slice(11, 16)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {loading ? (
        <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : aktywni.length === 0 ? (
        <Banner variant="info">Brak pracowników kuchni — admin ustawia dział „Kuchnia" w zakładce Pracownicy.</Banner>
      ) : (
        <>
          {/* Wybór dnia */}
          <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
            {dates.map((dt) => {
              const { wd, dm } = dayLabel(dt)
              const isW = [0, 6].includes(new Date(dt).getDay())
              const sel = dt === selectedDay
              return (
                <button
                  key={dt}
                  onClick={() => { setSelDay(dt); setDodaj(null); setEdycja(null) }}
                  className={`flex shrink-0 flex-col items-center rounded-xl border px-3.5 py-2 transition active:scale-[0.98] ${sel ? 'border-transparent bg-mint text-bg' : 'border-line bg-white/[0.03]'}`}
                  style={{ WebkitTapHighlightColor: 'transparent' }}
                >
                  <span className={`text-[10px] font-semibold uppercase tracking-wide ${sel ? 'text-bg' : isW ? 'text-blush' : 'text-muted'}`}>{wd}</span>
                  <span className={`text-sm font-semibold ${sel ? 'text-bg' : isW ? 'text-blush' : 'text-ink'}`}>{dm}</span>
                </button>
              )
            })}
          </div>

          <div className="space-y-3">
            {aktywni.map((p) => {
              const pAt = przyMap[`${selectedDay}_${p.id}`] || []
              const dodawanie = dodaj?.pracownik_id === p.id
              return (
                <div key={p.id} className="rounded-xl border border-line bg-white/[0.02] p-4">
                  <div className="mb-2 rounded-lg px-2 py-1 text-sm font-semibold text-ink" style={{ background: tloKoloru(p.kolor) }}>
                    {p.imie} {p.nazwisko}
                  </div>
                  <div className="flex flex-col gap-2">
                    {pAt.map((a) => {
                      const edytuje = edycja?.id === a.id
                      return (
                        <div key={a.id} className="rounded-lg border border-line border-l-[3px] border-l-mint bg-surface-2 p-2 text-xs">
                          <div className="flex items-center justify-between gap-2">
                            <span className="flex flex-wrap items-center gap-1.5 font-mono text-ink">
                              <Icon name="clock" className="h-3 w-3" /> {a.godz_od ? hhmm(a.godz_od) : 'Dowolnie'}
                            </span>
                            <div className="flex shrink-0 items-center gap-2">
                              <button onClick={() => setEdycja(edytuje ? null : { id: a.id, godz_od: a.godz_od || '' })} className="font-semibold text-muted transition hover:text-mint">{edytuje ? 'anuluj' : 'edytuj'}</button>
                              <button onClick={() => usun(a)} className="text-muted transition hover:text-danger" aria-label="Wykreśl ze zmiany"><Icon name="close" className="h-3.5 w-3.5" /></button>
                            </div>
                          </div>
                          {edytuje && (
                            <div className="mt-2 flex flex-col gap-1.5 border-t border-line pt-2">
                              <input type="time" value={edycja.godz_od} onChange={(ev) => setEdycja((x) => ({ ...x, godz_od: ev.target.value }))} className="rounded-md border border-line bg-surface p-1.5 text-ink outline-none" />
                              <button onClick={() => zapiszEdycje(a)} className="rounded-md bg-mint/20 py-1 font-semibold text-mint transition hover:bg-mint/30">Zapisz</button>
                            </div>
                          )}
                        </div>
                      )
                    })}

                    {dodawanie ? (
                      <div className="flex flex-col gap-1.5 rounded-lg border border-dashed border-mint/40 bg-surface-2 p-2 text-xs">
                        <input type="time" value={dodaj.godz_od} onChange={(ev) => setDodaj((d) => ({ ...d, godz_od: ev.target.value }))} className="rounded-md border border-line bg-surface p-1.5 text-ink outline-none" />
                        <div className="flex gap-1.5">
                          <button onClick={() => dodajZmiane(p.id)} className="flex-1 rounded-md bg-mint/20 py-1 font-semibold text-mint transition hover:bg-mint/30">Dodaj</button>
                          <button onClick={() => setDodaj(null)} className="rounded-md border border-line px-2 py-1 text-muted transition hover:text-ink">Anuluj</button>
                        </div>
                      </div>
                    ) : (
                      <button onClick={() => setDodaj({ pracownik_id: p.id, godz_od: '' })} className="rounded-lg border border-dashed border-line bg-surface-2 p-1.5 text-center text-xs font-medium text-muted transition hover:border-mint/50 hover:text-mint">+ dodaj zmianę</button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </Card>
  )
}
