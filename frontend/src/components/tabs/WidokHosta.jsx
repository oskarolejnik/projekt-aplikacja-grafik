import { useEffect, useState, useCallback, useRef } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../ui/Toast'

// Widok hosta — operacyjna tablica dnia: nadchodzący → na sali (timer obrotu) → zakończeni.
// Jedno kliknięcie „Posadź" dobiera stół silnikiem best-fit (auto) albo sadza na wybranym.
// Backend: /api/host/kolejka, /api/host/rezerwacja/{id}/faza|przydziel-stolik, /api/rezerwacje-stolik/{id}/auto-przydziel.

const dzisISO = () => new Date().toISOString().slice(0, 10)
const fld = 'rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-mint'

// Kolor timera obrotu: mięta < 90 min, cytryna 90–119, czerwień ≥ 120 (przekroczony zasiadek).
const timerKolor = (m) => (m == null ? 'text-muted' : m >= 120 ? 'text-danger' : m >= 90 ? 'text-lemon' : 'text-mint')

const FAZA_META = {
  posadzony: { l: 'Na sali', kol: 'bg-mint/15 text-mint' },
  rachunek: { l: 'Rachunek', kol: 'bg-lemon/15 text-lemon' },
  oplacony: { l: 'Opłacony', kol: 'bg-white/10 text-ink' },
}

export default function WidokHosta() {
  const { toast } = useToast()
  const { can, isAdmin } = useAuth()
  const canViewSensitive = isAdmin || can('rezerwacje.dane_wrazliwe')
  const canViewContacts = isAdmin || can('rezerwacje.dane_kontaktowe')
  const [data, setData] = useState(dzisISO())
  const dataRef = useRef(data)
  const [kolejka, setKolejka] = useState(null)
  const [stoliki, setStoliki] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)
  const [pick, setPick] = useState({})          // { [rid]: stolik_id } — ręczny wybór stołu
  const [actions, setActions] = useState({})
  const [rowFeedback, setRowFeedback] = useState({})
  const requestId = useRef(0)
  const hasDataRef = useRef(false)

  const load = useCallback(async ({ quiet = false, day = data } = {}) => {
    const id = ++requestId.current
    if (quiet) {
      setRefreshing(true)
      setRefreshError(null)
    } else {
      setRefreshing(false)
      setLoading(true)
      setLoadError(null)
    }
    try {
      const [kk, ss] = await Promise.all([api(`/host/kolejka?data=${day}`), api('/stoliki')])
      if (id !== requestId.current || day !== dataRef.current) return
      hasDataRef.current = true
      setKolejka(kk)
      setStoliki(ss.stoliki || [])
      setLoadError(null)
      setRefreshError(null)
    } catch (e) {
      if (id !== requestId.current || day !== dataRef.current) return
      const message = e.message || 'Nie udało się pobrać widoku hosta.'
      if (quiet && hasDataRef.current) setRefreshError(message)
      else setLoadError(message)
    } finally {
      if (id !== requestId.current || day !== dataRef.current) return
      setRefreshing(false)
      setLoading(false)
    }
  }, [data, canViewContacts, canViewSensitive])

  useEffect(() => { load() }, [load])
  // Cicha aktualizacja timerów obrotu co 30 s (bez migotania spinnera).
  useEffect(() => { const id = setInterval(() => load({ quiet: true }), 30000); return () => clearInterval(id) }, [load])

  const changeDay = (nextDay) => {
    if (!nextDay || nextDay === data) return
    dataRef.current = nextDay
    requestId.current += 1
    hasDataRef.current = false
    setKolejka(null)
    setLoading(true)
    setLoadError(null)
    setRefreshError(null)
    setRefreshing(false)
    setPick({})
    setRowFeedback({})
    setData(nextDay)
  }
  const przesun = (delta) => { const d = new Date(data); d.setDate(d.getDate() + delta); changeDay(d.toISOString().slice(0, 10)) }
  const stolikNazwa = (id) => stoliki.find((s) => s.id === id)?.nazwa || `#${id}`
  const stoleLabel = (r) => {
    const ids = [r.stolik_id, ...(r.stoliki_dodatkowe || [])].filter(Boolean)
    return ids.length ? ids.map(stolikNazwa).join(' + ') : null
  }

  const posadz = async (r) => {
    if (actions[r.id]) return
    const operationDay = data
    setActions((current) => ({ ...current, [r.id]: 'seat' }))
    setRowFeedback((current) => ({ ...current, [r.id]: null }))
    try {
      const sid = pick[r.id]
      await api(`/host/rezerwacja/${r.id}/posadz`, 'POST', {
        stolik_id: sid ? Number(sid) : null,
      })
      toast('Posadzono.', 'success')
      if (dataRef.current === operationDay) {
        setPick((p) => ({ ...p, [r.id]: '' }))
        void load({ day: operationDay })
      }
    } catch (e) {
      if (dataRef.current === operationDay) {
        setRowFeedback((current) => ({ ...current, [r.id]: e.message || 'Nie udało się posadzić gości.' }))
      }
      toast(e.message, 'error')
    } finally {
      setActions((current) => {
        const next = { ...current }
        delete next[r.id]
        return next
      })
    }
  }
  const faza = async (r, f) => {
    if (actions[r.id]) return
    const operationDay = data
    setActions((current) => ({ ...current, [r.id]: f }))
    setRowFeedback((current) => ({ ...current, [r.id]: null }))
    try {
      await api(`/host/rezerwacja/${r.id}/faza`, 'POST', { faza: f })
      if (dataRef.current === operationDay) void load({ day: operationDay })
    }
    catch (e) {
      if (dataRef.current === operationDay) {
        setRowFeedback((current) => ({ ...current, [r.id]: e.message || 'Nie udało się zmienić etapu.' }))
      }
      toast(e.message, 'error')
    } finally {
      setActions((current) => {
        const next = { ...current }
        delete next[r.id]
        return next
      })
    }
  }

  const dataLabel = new Date(data).toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' })
  const P = kolejka?.podsumowanie || {}
  const wolneStoly = stoliki.filter((s) => s.aktywny)

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Widok hosta" subtitle="Operacyjna tablica dnia: kto nadchodzi, kto na sali, timer obrotu. „Posadź” dobiera stół automatycznie." />
        <div className="flex items-center gap-2">
          <button onClick={() => przesun(-1)} aria-label="Poprzedni dzień" className="min-h-11 min-w-11 rounded-xl border border-line px-3 py-1.5 text-lg leading-none text-muted transition hover:text-ink active:scale-[0.98]">‹</button>
          <label className="sr-only" htmlFor="host-day">Dzień widoku hosta</label>
          <input id="host-day" type="date" value={data} onChange={(e) => changeDay(e.target.value)} className={`${fld} min-h-11`} />
          <button onClick={() => przesun(1)} aria-label="Następny dzień" className="min-h-11 min-w-11 rounded-xl border border-line px-3 py-1.5 text-lg leading-none text-muted transition hover:text-ink active:scale-[0.98]">›</button>
          <button onClick={() => changeDay(dzisISO())} className="min-h-11 rounded-xl border border-line px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-ink active:scale-[0.98]">Dzisiaj</button>
        </div>
      </div>

      {/* Podsumowanie dnia pokazujemy dopiero dla potwierdzonych danych — awaria nie może
          wyglądać jak cztery zera i pusta sala. */}
      {kolejka ? (
        <div className="mb-5 flex flex-wrap gap-2.5">
          <Kafelek ikona="clock" etykieta="Nadchodzący" wartosc={P.nadchodzace ?? 0} />
          <Kafelek ikona="users" etykieta="Na sali" wartosc={P.na_sali ?? 0} akcent />
          <Kafelek ikona="sparkles" etykieta="Covery na sali" wartosc={P.coverow_na_sali ?? 0} />
          <Kafelek ikona="check" etykieta="Zakończeni" wartosc={P.zakonczone ?? 0} />
          <span className="ml-auto self-center text-sm font-medium capitalize text-muted">{dataLabel}</span>
          <span className="inline-flex min-h-5 items-center gap-1.5 self-center text-xs text-muted" role="status" aria-live="polite">
            {refreshing ? <><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Aktualizuję…</> : null}
          </span>
        </div>
      ) : null}

      {refreshError && kolejka ? (
        <Banner variant="warn" className="mb-4">
          <div className="flex flex-wrap items-center gap-3">
            <span>Dane mogą być nieaktualne: {refreshError}</span>
            <Button variant="ghost" size="sm" onClick={() => load({ quiet: true })}>Ponów</Button>
          </div>
        </Banner>
      ) : null}

      {loading ? (
        <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : loadError ? (
        <div role="alert">
          <Banner variant="danger">
            <div className="space-y-3">
              <p>Nie udało się pobrać kolejki: {loadError}</p>
              <Button variant="ghost" size="sm" onClick={() => load()}>Spróbuj ponownie</Button>
            </div>
          </Banner>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {/* Nadchodzący */}
          <Lane tytul="Nadchodzący" licznik={kolejka?.nadchodzace?.length || 0}>
            {(kolejka?.nadchodzace || []).length === 0 && <Pusto>Nikt nie czeka na wejście.</Pusto>}
            {(kolejka?.nadchodzace || []).map((r) => (
              <div key={r.id} className="rounded-xl border border-line bg-surface-2 px-3.5 py-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-display text-sm font-bold tabular-nums text-ink">{r.godz_od || '—'}</span>
                  {r.faza_hosta === 'przybyl' && <span className="rounded-full bg-lemon/15 px-2 py-0.5 text-[11px] font-semibold text-lemon">Przybył</span>}
                </div>
                <div className="mt-0.5 text-sm font-semibold text-ink">{canViewContacts ? r.nazwisko : 'Gość'}</div>
                <div className="text-xs text-muted">
                  {r.liczba_osob ? `${r.liczba_osob} os.` : ''}{stoleLabel(r) ? ` · stół ${stoleLabel(r)}` : ' · bez stołu'}
                </div>
                <DaneWrazliwe gosc={r.gosc} visible={canViewSensitive} />
                <div className="mt-2.5 flex items-center gap-1.5">
                  <label className="sr-only" htmlFor={`host-table-${r.id}`}>Stół dla {canViewContacts ? r.nazwisko : 'gościa'}</label>
                  <select id={`host-table-${r.id}`} value={pick[r.id] || ''} disabled={!!actions[r.id]} onChange={(e) => setPick((p) => ({ ...p, [r.id]: e.target.value }))} className={`${fld} min-h-11 min-w-0 flex-1`} title="Wybierz stół ręcznie (puste = auto)">
                    <option value="">auto (best-fit)</option>
                    {wolneStoly.map((s) => <option key={s.id} value={s.id}>{s.nazwa} · {s.pojemnosc} os.</option>)}
                  </select>
                  <Button onClick={() => posadz(r)} disabled={!!actions[r.id]} loading={actions[r.id] === 'seat'} loadingLabel="Sadzam…" className="shrink-0 px-3 py-1.5 text-xs"><Icon name="check" className="h-4 w-4" /> Posadź</Button>
                </div>
                {rowFeedback[r.id] ? <p role="alert" className="mt-2 text-xs text-danger">{rowFeedback[r.id]}</p> : null}
              </div>
            ))}
          </Lane>

          {/* Na sali */}
          <Lane tytul="Na sali" licznik={kolejka?.na_sali?.length || 0} akcent>
            {(kolejka?.na_sali || []).length === 0 && <Pusto>Sala pusta.</Pusto>}
            {(kolejka?.na_sali || []).map((r) => {
              const meta = FAZA_META[r.faza_hosta] || FAZA_META.posadzony
              return (
                <div key={r.id} className="rounded-xl border border-line bg-surface-2 px-3.5 py-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-semibold text-ink">{canViewContacts ? r.nazwisko : 'Gość'}</span>
                    <span className={`shrink-0 font-display text-sm font-bold tabular-nums ${timerKolor(r.minuty_od_posadzenia)}`}>
                      {r.minuty_od_posadzenia != null ? `${r.minuty_od_posadzenia}′` : ''}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                    <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-semibold text-ink">{stoleLabel(r) || '—'}</span>
                    {r.liczba_osob ? <span>{r.liczba_osob} os.</span> : null}
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${meta.kol}`}>{meta.l}</span>
                  </div>
                  <DaneWrazliwe gosc={r.gosc} visible={canViewSensitive} />
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    {r.faza_hosta === 'posadzony' && <FazaBtn disabled={!!actions[r.id]} onClick={() => faza(r, 'rachunek')} ikona="clipboard">Rachunek</FazaBtn>}
                    {(r.faza_hosta === 'posadzony' || r.faza_hosta === 'rachunek') && <FazaBtn disabled={!!actions[r.id]} onClick={() => faza(r, 'oplacony')} ikona="check">Opłacony</FazaBtn>}
                    <FazaBtn disabled={!!actions[r.id]} onClick={() => faza(r, 'wyszedl')} ikona="close" wyroznij>Wyszedł</FazaBtn>
                  </div>
                  {rowFeedback[r.id] ? <p role="alert" className="mt-2 text-xs text-danger">{rowFeedback[r.id]}</p> : null}
                </div>
              )
            })}
          </Lane>

          {/* Zakończeni + waitlista */}
          <Lane tytul="Zakończeni" licznik={kolejka?.zakonczone?.length || 0} przygaszony>
            {(kolejka?.zakonczone || []).length === 0 && <Pusto>Jeszcze nikt nie wyszedł.</Pusto>}
            {(kolejka?.zakonczone || []).map((r) => (
              <div key={r.id} className="flex items-center justify-between gap-2 rounded-lg border border-line/60 px-3 py-2 text-sm">
                <span className="text-muted"><span className="font-medium text-ink/80">{canViewContacts ? r.nazwisko : 'Gość'}</span>{stoleLabel(r) ? ` · ${stoleLabel(r)}` : ''}</span>
                <span className="text-[11px] text-muted">{r.status === 'no_show' ? 'nie przyszli' : 'odbyła się'}</span>
              </div>
            ))}
            {(kolejka?.waitlista || []).length > 0 && (
              <div className="mt-3 border-t border-line pt-3">
                <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">Lista oczekujących</div>
                {kolejka.waitlista.map((w) => (
                  <div key={w.id} className="flex items-center justify-between gap-2 py-1 text-sm">
                    <span className="text-ink/80">{canViewContacts ? w.nazwisko : 'Gość'}</span>
                    <span className="text-xs text-muted">{[w.godz_od, w.liczba_osob ? `${w.liczba_osob} os.` : ''].filter(Boolean).join(' · ')}</span>
                  </div>
                ))}
              </div>
            )}
          </Lane>
        </div>
      )}
    </Card>
  )
}

function Kafelek({ ikona, etykieta, wartosc, akcent }) {
  return (
    <div className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-2 ${akcent ? 'border-mint/30 bg-mint/[0.07]' : 'border-line bg-surface-2'}`}>
      <Icon name={ikona} className={`h-4 w-4 ${akcent ? 'text-mint' : 'text-muted'}`} />
      <div>
        <div className="font-display text-lg font-bold leading-none tabular-nums text-ink">{wartosc}</div>
        <div className="text-[11px] text-muted">{etykieta}</div>
      </div>
    </div>
  )
}

function Lane({ tytul, licznik, akcent, przygaszony, children }) {
  return (
    <div className={`rounded-2xl border p-3 ${akcent ? 'border-mint/25 bg-mint/[0.04]' : 'border-line bg-surface/40'}`}>
      <div className="mb-2.5 flex items-center gap-2 px-1">
        <h3 className={`font-display text-sm font-bold ${przygaszony ? 'text-muted' : 'text-ink'}`}>{tytul}</h3>
        <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[11px] font-semibold tabular-nums text-muted">{licznik}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function Pusto({ children }) {
  return <div className="rounded-xl border border-dashed border-line px-3 py-8 text-center text-xs text-muted">{children}</div>
}

function FazaBtn({ onClick, ikona, children, wyroznij, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`inline-flex min-h-11 items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-semibold transition active:scale-[0.98] ${
        wyroznij ? 'border-line text-muted hover:border-danger/40 hover:text-danger' : 'border-line text-muted hover:text-ink'} disabled:cursor-wait disabled:opacity-50`}>
      <Icon name={ikona} className="h-3.5 w-3.5" /> {children}
    </button>
  )
}

function DaneWrazliwe({ gosc, visible }) {
  if (!visible || !gosc || (!gosc.ma_alergie && !gosc.alergie)) return null
  return (
    <div className="mt-2 flex items-start gap-1.5 rounded-lg bg-danger/10 px-2 py-1.5 text-xs font-medium text-danger">
      <Icon name="warning" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{gosc.alergie ? `Alergie: ${gosc.alergie}` : 'Alergie — sprawdź profil gościa'}</span>
    </div>
  )
}
