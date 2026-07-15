import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useData } from '../context/DataContext'
import { useToast } from '../components/ui/Toast'
import { WeekSelect } from '../components/ui/WeekSelect'
import { Card } from '../components/ui/Card'
import { Banner } from '../components/ui/Banner'
import { Button } from '../components/ui/Button'
import { Hint } from '../components/ui/Hint'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { ddmmyyyy, hhmm, NAZWY_DNI, zakresDni } from '../lib/format'
import { BOUNCE } from '../lib/motion'
import MojeUrlopy from '../components/MojeUrlopy'
import { PillSwitch } from '../components/ui/PillSwitch'

// Godzina imprezy z arkusza bywa łańcuchem ("14:30:00", "Brak", "None"...).
const fmtGodzina = (g) => {
  if (!g || g === 'None' || g === 'Brak') return ''
  const m = String(g).match(/^(\d{1,2}):(\d{2})/)
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : String(g)
}

const snapshotDni = (items) => JSON.stringify(items.map(({ data, dostepnosc, od, do: godzDo }) => ({
  data,
  dostepnosc,
  od,
  do: godzDo,
})))

// Treść widoku „Moja dyspozycyjność" (nagłówek/powłokę dostarcza EmployeeArea).
// Domyślnie pokazujemy tydzień PRZYSZŁY (dyspozycje składa się z wyprzedzeniem).
// Zapisaną dyspozycyjność wczytujemy z serwera, więc pracownik widzi, co zaznaczył,
// i może to zmieniać aż do publikacji grafiku (potem widok jest zablokowany).
export default function EmployeeAvailability({ onDirtyChange }) {
  const { week, przyszly, setWeek } = useData()
  const { confirm } = useToast()
  const [dni, setDni] = useState([])
  const [imprezyMap, setImprezyMap] = useState({})
  const [rezerwacjeMap, setRezerwacjeMap] = useState({})
  const [zablokowane, setZablokowane] = useState(false) // grafik opublikowany -> read-only
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState(null)
  const [savedSnapshot, setSavedSnapshot] = useState(null)
  const [savedAt, setSavedAt] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const reqId = useRef(0) // chroni przed wyścigiem: stare ładowanie nie nadpisze nowego (zmiana tygodnia)

  // Na wejściu w widok ustaw tydzień przyszły (raz, przy montażu).
  useEffect(() => {
    setWeek(przyszly)
  }, [przyszly, setWeek])

  const [s, e] = week.split('|')
  const daty = useMemo(() => zakresDni(s, e), [s, e])

  const load = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    setLoadError(null)
    setSaveError(null)
    setSavedAt(null)
    try {
      const [existing, imprezy, rez, grafik] = await Promise.all([
        api(`/me/dyspozycje?start=${s}&end=${e}`),
        api(`/me/imprezy?start=${s}&end=${e}`),
        api('/me/rezerwacje').catch(() => ({ dni: [] })),
        api(`/me/grafik?start=${s}&end=${e}`).catch(() => ({ opublikowany: false })),
      ])
      if (id !== reqId.current) return // starsze zapytanie (tydzień się zmienił) — pomiń wynik
      setZablokowane(!!grafik?.opublikowany)
      setRezerwacjeMap(Object.fromEntries((rez?.dni || []).map((d) => [d.data, d])))
      const map = Object.fromEntries(existing.map((d) => [d.data, d]))
      const nextDni = daty.map((d) => {
        const rec = map[d]
        return {
          data: d,
          dostepnosc: rec ? rec.dostepnosc : true, // domyślnie dostępny
          od: rec && rec.godz_od ? hhmm(rec.godz_od) : '',
          do: rec && rec.godz_do ? hhmm(rec.godz_do) : '',
        }
      })
      setDni(nextDni)
      // Brak choć jednego rekordu oznacza, że widoczne domyślne wartości
      // nie zostały jeszcze jawnie zapisane dla całego tygodnia.
      setSavedSnapshot(daty.every((d) => map[d]) ? snapshotDni(nextDni) : null)
      const im = {}
      imprezy.forEach((x) => {
        ;(im[x.data] = im[x.data] || []).push(x)
      })
      setImprezyMap(im)
    } catch (err) {
      if (id === reqId.current) setLoadError(err.message || 'Nie udało się wczytać dyspozycyjności.')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [s, e, daty])

  useEffect(() => {
    load()
  }, [load])

  const currentSnapshot = useMemo(() => snapshotDni(dni), [dni])
  const dirty = !loading && !loadError && !zablokowane && currentSnapshot !== savedSnapshot

  useEffect(() => {
    onDirtyChange?.(dirty)
    return () => {
      if (dirty) onDirtyChange?.(false)
    }
  }, [dirty, onDirtyChange])

  useEffect(() => {
    if (!dirty) return undefined
    const warnBeforeUnload = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [dirty])

  const confirmWeekChange = useCallback(async () => {
    if (!dirty) return true
    return confirm('Masz niezapisane zmiany dyspozycyjności. Zmienić okres i je odrzucić?', {
      title: 'Niezapisane zmiany',
      confirmText: 'Zmień okres',
    })
  }, [dirty, confirm])

  const setDay = (idx, patch) => {
    setSaveError(null)
    setDni((cur) => cur.map((d, i) => (i === idx ? { ...d, ...patch } : d)))
  }

  const zapisz = async () => {
    if (saving || loading || loadError || !dirty) return
    const submittedSnapshot = currentSnapshot
    setSaving(true)
    setSaveError(null)
    try {
      await api('/me/dyspozycje', 'PUT', {
        dyspozycje: dni.map((d) => ({
          data: d.data,
          dostepnosc: d.dostepnosc,
          godz_od: d.dostepnosc && d.od ? `${d.od}:00` : null,
          godz_do: d.dostepnosc && d.do ? `${d.do}:00` : null,
        })),
      })
      setSavedSnapshot(submittedSnapshot)
      setSavedAt(new Date())
    } catch (err) {
      // 409 = grafik opublikowany w międzyczasie -> zablokuj i przeładuj zapisany stan.
      if (/opublikowan/i.test(err.message)) {
        setZablokowane(true)
        load()
      } else {
        setSaveError(err.message || 'Nie udało się zapisać dyspozycyjności.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-1.5">
          <WeekSelect beforeChange={confirmWeekChange} />
          <Hint>Zaznacz dni, w których możesz pracować. Domyślnie „Cały dzień” — wyłącz przełącznik, aby podać godziny od–do.</Hint>
        </div>
      </div>

      {zablokowane && (
        <div className="mb-4 flex items-center gap-2.5 rounded-xl border border-line bg-white/[0.03] px-4 py-3 text-sm font-semibold text-muted">
          <Icon name="check" className="h-4 w-4 text-success" />
          Grafik opublikowany. Poniżej Twoja zapisana dyspozycyjność (tylko do podglądu).
        </div>
      )}

      <Card className="p-6">
        {loadError ? (
          <div role="alert">
            <Banner variant="danger">
              <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
                <span>Nie udało się wczytać dyspozycyjności. {loadError}</span>
                <Button size="sm" variant="ghost" onClick={load}>Spróbuj wczytać ponownie</Button>
              </div>
            </Banner>
          </div>
        ) : loading ? (
          <div className="grid place-items-center py-16">
            <Spinner className="h-6 w-6 text-muted" />
          </div>
        ) : (
          <div className={`space-y-3 ${zablokowane ? 'pointer-events-none select-none opacity-70' : ''}`}>
            {dni.map((d, i) => {
              const imprezy = imprezyMap[d.data] || []
              const rez = rezerwacjeMap[d.data]
              const calyDzien = !d.od && !d.do
              return (
                <div
                  key={d.data}
                  className="animate-fade-up rounded-xl border border-line bg-white/[0.02] p-4"
                  style={{ animationDelay: `${Math.min(i, 8) * 55}ms`, animationDuration: '480ms' }}
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-[150px]">
                      <div className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(d.data).getDay()]}</div>
                      <div className="text-xs text-muted">{ddmmyyyy(d.data)}</div>
                      {rez && rez.liczba > 0 && (
                        <div className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-blush/10 px-1.5 py-0.5 text-[11px] font-semibold text-blush">
                          <Icon name="calendar" className="h-3 w-3" /> {rez.liczba} rez. · {rez.osoby} os.
                        </div>
                      )}
                    </div>

                    <div className="flex w-full flex-col sm:w-auto sm:items-end">
                      {/* Pill switcher (CSS) — wskaźnik sukces/danger sunie pod aktywnym stanem. */}
                      <PillSwitch
                        className="w-full sm:w-60"
                        value={d.dostepnosc}
                        onChange={(v) => setDay(i, { dostepnosc: v })}
                        options={[
                          { value: true, label: 'Dostępny', activeBg: 'bg-success', activeText: 'text-bg' },
                          { value: false, label: 'Niedostępny', activeBg: 'bg-danger', activeText: 'text-white' },
                        ]}
                      />

                      {/* Zwijanie opcji (Dostępny→Niedostępny) PIONOWO: grid-template-rows 0fr↔1fr. */}
                      <div
                        className="grid w-full transition-all duration-[450ms] ease-[cubic-bezier(0.22,1,0.36,1)] sm:w-auto"
                        style={{ gridTemplateRows: d.dostepnosc ? '1fr' : '0fr', opacity: d.dostepnosc ? 1 : 0 }}
                      >
                        <div className="min-h-0 overflow-hidden">
                          <div className="flex flex-col items-stretch gap-2 pt-2 text-xs sm:items-end">
                            <button
                              type="button"
                              role="switch"
                              aria-checked={calyDzien}
                              onClick={() => setDay(i, calyDzien ? { od: '08:00', do: '' } : { od: '', do: '' })}
                              className="flex shrink-0 items-center gap-2 self-start font-semibold text-muted transition active:scale-[0.96] sm:self-end"
                              style={{ WebkitTapHighlightColor: 'transparent' }}
                            >
                              <span className={`relative inline-flex h-6 w-11 items-center rounded-full px-0.5 transition-colors duration-200 ${calyDzien ? 'bg-success' : 'bg-white/15'}`}>
                                <span
                                  className="h-5 w-5 rounded-full bg-white shadow-sm will-change-transform"
                                  style={{ transform: `translateX(${calyDzien ? 20 : 0}px)`, transition: `transform 450ms ${BOUNCE}` }}
                                />
                              </span>
                              Cały dzień
                            </button>

                            {/* Pola od–do wyjeżdżają w dół, gdy „Cały dzień" jest wyłączony. */}
                            <div
                              className="grid transition-all duration-[450ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
                              style={{ gridTemplateRows: calyDzien ? '0fr' : '1fr', opacity: calyDzien ? 0 : 1 }}
                            >
                              <div className="min-h-0 overflow-hidden">
                                <div className="flex flex-wrap items-center gap-2 pt-1 text-muted sm:justify-end">
                                  <span>od</span>
                                  <input
                                    type="time"
                                    value={d.od}
                                    onChange={(ev) => setDay(i, { od: ev.target.value })}
                                    className="field px-2 py-2"
                                    style={{ width: '7rem' }}
                                  />
                                  <span>do</span>
                                  <input
                                    type="time"
                                    value={d.do}
                                    onChange={(ev) => setDay(i, { do: ev.target.value })}
                                    className="field px-2 py-2"
                                    style={{ width: '7rem' }}
                                  />
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {imprezy.length > 0 && (
                    <div className="mt-3 space-y-1.5 border-t border-line pt-3">
                      <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-blush">
                        <Icon name="calendar" className="h-3.5 w-3.5" /> Imprezy tego dnia
                      </div>
                      {imprezy.map((imp) => (
                        <div key={imp.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 pl-5 text-xs">
                          <span className="font-semibold text-ink">
                            {imp.sala && !['Brak', 'None', ''].includes(String(imp.sala)) ? `Sala ${imp.sala}` : 'Impreza'}
                          </span>
                          {fmtGodzina(imp.godzina) && (
                            <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 font-mono font-semibold text-ink">{fmtGodzina(imp.godzina)}</span>
                          )}
                          {imp.liczba_osob > 0 && <span className="text-muted">· {imp.liczba_osob} os.</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {!zablokowane && !loadError && (
          <>
            {saveError && (
              <div className="mt-6" role="alert">
                <Banner variant="danger">Nie udało się zapisać zmian. {saveError}</Banner>
              </div>
            )}
            <div className={`${saveError ? 'mt-3' : 'mt-6'} sticky bottom-3 z-20 flex flex-col gap-3 rounded-2xl border border-line bg-surface-2/95 p-4 shadow-lg shadow-black/30 backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between`}>
              <span className={`text-sm ${saveError ? 'text-danger' : dirty ? 'text-lemon' : 'text-muted'}`} aria-live="polite">
                {loading
                  ? 'Wczytuję zapisaną dyspozycyjność…'
                  : saving
                    ? 'Zapisuję zmiany dla wybranego tygodnia…'
                    : saveError
                      ? 'Zmiany nadal są na ekranie — możesz spróbować ponownie.'
                      : dirty
                        ? 'Masz niezapisane zmiany.'
                        : savedAt
                          ? `Zapisano o ${savedAt.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}`
                          : 'Dyspozycyjność jest zapisana.'}
              </span>
              <Button
                onClick={zapisz}
                disabled={loading || !dirty}
                loading={saving}
                loadingLabel="Zapisywanie…"
                className="w-full sm:w-auto"
              >
                <Icon name={saveError ? 'refresh' : 'check'} className="h-4 w-4" />
                {saveError ? 'Spróbuj ponownie' : 'Zapisz dyspozycyjność'}
              </Button>
            </div>
          </>
        )}
      </Card>

      <details className="group mt-6">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 rounded-xl border border-line bg-white/[0.03] px-4 py-3 transition hover:bg-white/[0.05] [&::-webkit-details-marker]:hidden">
          <span>
            <span className="block font-semibold text-ink">Urlopy i nieobecności</span>
            <span className="block text-xs text-muted">Złóż wniosek lub sprawdź jego status</span>
          </span>
          <Icon name="chevronDown" className="h-4 w-4 shrink-0 text-muted transition-transform duration-200 group-open:rotate-180" />
        </summary>
        <MojeUrlopy />
      </details>
    </>
  )
}
