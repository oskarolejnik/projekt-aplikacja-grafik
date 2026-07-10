import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { Card } from '../ui/Card'
import { Hint } from '../ui/Hint'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { WeekSelect } from '../ui/WeekSelect'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, hhmm, NAZWY_DNI } from '../../lib/format'
import { generujOpcjeTygodni } from '../../lib/weeks'

const requirementPayload = (w) => ({
  data: w.data,
  stanowisko_id: w.stanowisko_id,
  liczba_osob: w.liczba_osob,
  godz_od: w.godz_od || null,
  rewir: w.rewir || null,
  jest_impreza: !!w.jest_impreza,
})

const emptyRequirementForm = (data) => ({
  data,
  stanowisko: '',
  podkategoria: '',
  godzina: '',
  liczba: 1,
  rewir: '',
  dirty: false,
})

// Pojedyncze wymaganie w karcie dnia — szybka edycja z lokalnym feedbackiem.
function WymRow({ w, nazwa, onSaved, onDeleted, onRestored, onBusyChange }) {
  const { toast } = useToast()
  const [liczba, setLiczba] = useState(w.liczba_osob)
  const [action, setAction] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const actionRef = useRef(null)

  useEffect(() => {
    setLiczba(w.liczba_osob)
  }, [w.liczba_osob])

  const begin = (nextAction) => {
    if (actionRef.current) return false
    actionRef.current = nextAction
    setAction(nextAction)
    setFeedback(null)
    onBusyChange?.(true)
    return true
  }

  const finish = () => {
    actionRef.current = null
    setAction(null)
    onBusyChange?.(false)
  }

  const save = async () => {
    if (actionRef.current || +liczba === w.liczba_osob) return
    const nextValue = Number(liczba)
    if (!Number.isInteger(nextValue) || nextValue < 1) {
      setFeedback({ type: 'error', message: 'Podaj co najmniej 1 osobę.' })
      return
    }
    if (!begin('save')) return
    try {
      const saved = await api('/wymagania', 'POST', { ...requirementPayload(w), liczba_osob: nextValue })
      onSaved(saved)
      setFeedback({ type: 'success', message: 'Zapisano' })
    } catch (e) {
      setFeedback({ type: 'error', message: e.message || 'Nie udało się zapisać.' })
    } finally {
      finish()
    }
  }

  const usun = async () => {
    if (!begin('delete')) return
    try {
      await api(`/wymagania/${w.id}`, 'DELETE')
      onDeleted(w.id)
      toast(`Usunięto wymaganie: ${nazwa}.`, 'info', {
        action: {
          label: 'Cofnij',
          onClick: async () => {
            try {
              const restored = await api('/wymagania', 'POST', requirementPayload(w))
              onRestored(restored)
              toast('Przywrócono wymaganie.', 'success')
            } catch (error) {
              toast(error.message || 'Nie udało się przywrócić wymagania.', 'error')
            }
          },
        },
      })
    } catch (e) {
      setFeedback({ type: 'error', message: e.message || 'Nie udało się usunąć.' })
    } finally {
      finish()
    }
  }

  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 ${w.jest_impreza ? 'border-info/30 bg-info/10' : 'border-line bg-white/[0.03]'}`}>
      <div>
        <div className="flex items-center gap-2 text-sm font-bold text-ink">
          {nazwa}
          {w.jest_impreza && <span className="rounded-md bg-info/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-info">Impreza</span>}
        </div>
        {w.rewir && <div className="mt-0.5 text-xs font-medium text-mint">{w.rewir}</div>}
        <div className="mt-1 flex items-center gap-1 text-xs text-muted">
          <Icon name="clock" className="h-3 w-3" /> {w.godz_od ? hhmm(w.godz_od) : 'Dowolna'}
        </div>
      </div>
      <div className="flex min-w-[11rem] flex-col items-end gap-1.5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <label htmlFor={`wymaganie-${w.id}`} className="text-[10px] font-semibold uppercase text-muted">Osób</label>
            <input
              id={`wymaganie-${w.id}`}
              aria-label={`Liczba osób: ${nazwa}, ${ddmmyyyy(w.data)}`}
              type="number"
              min="1"
              value={liczba}
              disabled={!!action}
              onChange={(e) => {
                setLiczba(e.target.value)
                setFeedback(null)
              }}
              onBlur={save}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur()
              }}
              className="field w-16 px-2 py-2 text-center text-lg font-semibold"
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={usun}
            disabled={!!action}
            loading={action === 'delete'}
            loadingLabel="Usuwam…"
            className="border-danger/20 px-2 text-danger hover:bg-danger/10"
            aria-label={`Usuń wymaganie: ${nazwa}, ${ddmmyyyy(w.data)}`}
          >
            <Icon name="trash" className="h-4 w-4" />
          </Button>
        </div>
        <span
          role={feedback?.type === 'error' ? 'alert' : 'status'}
          aria-live="polite"
          className={`min-h-4 text-xs ${feedback?.type === 'error' ? 'text-danger' : feedback?.type === 'success' ? 'text-success' : 'text-muted'}`}
        >
          {action === 'save' ? 'Zapisuję…' : feedback?.message || ''}
        </span>
      </div>
    </div>
  )
}

export default function Wymagania({ active = true }) {
  const { stanowiska, week, reloadDicts } = useData()
  const [wymagania, setWymagania] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)
  const [rowBusyCount, setRowBusyCount] = useState(0)
  const reqId = useRef(0)
  const [s, e] = week.split('|')
  const rangeRef = useRef({ s, e })
  rangeRef.current = { s, e }

  // Osobny szkic dla każdego tygodnia: zmiana okresu nie kasuje rozpoczętego formularza.
  const [formsByWeek, setFormsByWeek] = useState({})
  const form = formsByWeek[week] || emptyRequirementForm(s)
  const [adding, setAdding] = useState(false)
  const [addFeedback, setAddFeedback] = useState(null)

  // Kopiowanie tygodnia
  const tygodnie = useMemo(() => generujOpcjeTygodni(), [])
  const [kopFrom, setKopFrom] = useState(tygodnie.domyslny)
  const [kopTo, setKopTo] = useState('')
  const [copying, setCopying] = useState(false)
  const [copyFeedback, setCopyFeedback] = useState(null)

  const stanMap = useMemo(() => Object.fromEntries(stanowiska.map((s) => [s.id, s])), [stanowiska])
  const wybraneStan = stanMap[+form.stanowisko]
  const podkategorie = wybraneStan?.podkategorie || []

  const load = useCallback(async ({ silent = false } = {}) => {
    const id = ++reqId.current
    if (silent) {
      setRefreshing(true)
      setRefreshError(null)
    } else {
      setLoading(true)
      setLoadError(null)
    }
    try {
      await reloadDicts()
      const next = await api(`/wymagania?start=${s}&end=${e}`)
      if (id !== reqId.current) return false
      setWymagania(next)
      return true
    } catch (err) {
      if (id !== reqId.current) return false
      if (silent) setRefreshError(err.message || 'Nie udało się odświeżyć planu.')
      else setLoadError(err.message || 'Nie udało się wczytać planu obsady.')
      return false
    } finally {
      if (id === reqId.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [s, e, reloadDicts])

  useEffect(() => {
    if (active) load()
  }, [active, load])

  useEffect(() => {
    setAddFeedback(null)
    setCopyFeedback(null)
    setRefreshError(null)
  }, [week])

  const updateForm = (patch) => {
    setAddFeedback(null)
    setFormsByWeek((current) => ({
      ...current,
      [week]: { ...(current[week] || emptyRequirementForm(s)), ...patch, dirty: true },
    }))
  }

  const onSubcat = (val) => {
    const pk = podkategorie.find((x) => x.id === +val)
    updateForm({
      podkategoria: val,
      ...(pk ? { rewir: pk.nazwa || '', godzina: pk.godz_od ? hhmm(pk.godz_od) : '' } : {}),
    })
  }

  const upsertRequirement = useCallback((saved) => {
    setWymagania((current) => {
      const withoutSaved = current.filter((item) => item.id !== saved.id)
      const { s: currentStart, e: currentEnd } = rangeRef.current
      return saved.data >= currentStart && saved.data <= currentEnd ? [...withoutSaved, saved] : withoutSaved
    })
  }, [])

  const removeRequirement = useCallback((id) => {
    setWymagania((current) => current.filter((item) => item.id !== id))
  }, [])

  const setRowBusy = useCallback((busy) => {
    setRowBusyCount((count) => Math.max(0, count + (busy ? 1 : -1)))
  }, [])

  const dodaj = async () => {
    if (adding) return
    if (!form.stanowisko) {
      setAddFeedback({ type: 'error', message: 'Wybierz stanowisko.' })
      return
    }
    if (!form.data || form.data < s || form.data > e) {
      setAddFeedback({ type: 'error', message: 'Wybierz dzień należący do aktualnego tygodnia.' })
      return
    }
    const people = Number(form.liczba)
    if (!Number.isInteger(people) || people < 1) {
      setAddFeedback({ type: 'error', message: 'Podaj co najmniej 1 osobę.' })
      return
    }
    setAdding(true)
    setAddFeedback(null)
    try {
      const saved = await api('/wymagania', 'POST', {
        data: form.data,
        stanowisko_id: +form.stanowisko,
        liczba_osob: people,
        godz_od: form.godzina ? `${form.godzina}:00` : null,
        rewir: form.rewir.trim() || null,
      })
      upsertRequirement(saved)
      setFormsByWeek((current) => ({
        ...current,
        [week]: { ...(current[week] || form), dirty: false },
      }))
      setAddFeedback({ type: 'success', message: `Dodano do planu: ${stanMap[saved.stanowisko_id]?.nazwa || 'stanowisko'}, ${ddmmyyyy(saved.data)}.` })
    } catch (e) {
      setAddFeedback({ type: 'error', message: e.message || 'Nie udało się dodać wymagania.' })
    } finally {
      setAdding(false)
    }
  }

  const kopiuj = async () => {
    if (copying) return
    if (!kopFrom || !kopTo) {
      setCopyFeedback({ type: 'error', message: 'Wybierz tydzień źródłowy i docelowy.' })
      return
    }
    if (kopFrom === kopTo) {
      setCopyFeedback({ type: 'error', message: 'Wybierz dwa różne tygodnie.' })
      return
    }
    setCopying(true)
    setCopyFeedback(null)
    try {
      const r = await api('/wymagania/kopiuj-tydzien', 'POST', {
        source_start: kopFrom.split('|')[0],
        target_start: kopTo.split('|')[0],
      })
      setCopyFeedback({ type: 'success', message: `Skopiowano ${r.skopiowano ?? 0} wymagań.` })
      if (kopTo.split('|')[0] === s) await load({ silent: true })
    } catch (e) {
      setCopyFeedback({ type: 'error', message: e.message || 'Nie udało się skopiować tygodnia.' })
    } finally {
      setCopying(false)
    }
  }

  const actionBusy = loading || refreshing || adding || copying || rowBusyCount > 0
  const hasDirtyDraft = Object.values(formsByWeek).some((item) => item.dirty)

  const przejdzDoDodawania = () => {
    document.getElementById('wymagania-dodaj')?.scrollIntoView({ block: 'start' })
    setTimeout(() => document.getElementById('wymagania-stanowisko')?.focus(), 0)
  }

  useEffect(() => {
    if (!hasDirtyDraft) return undefined
    const warnBeforeUnload = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [hasDirtyDraft])

  // Grupowanie po dniu
  const dni = useMemo(() => {
    const map = {}
    wymagania.forEach((w) => {
      ;(map[w.data] = map[w.data] || []).push(w)
    })
    return Object.keys(map)
      .sort()
      .map((d) => ({ data: d, items: map[d] }))
  }, [wymagania])

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <WeekSelect disabled={actionBusy} />
        <div className="flex flex-wrap items-center gap-3 md:justify-end">
          <span className="inline-flex min-h-5 items-center gap-2 text-sm text-muted" role="status" aria-live="polite">
            {refreshing && <Spinner className="h-3.5 w-3.5" />}
            {refreshing ? 'Aktualizuję plan…' : 'Zaplanowane wymagania na wybrany tydzień'}
          </span>
          <Button size="sm" onClick={przejdzDoDodawania} disabled={loading || !!loadError}>
            <Icon name="plus" className="h-4 w-4" /> Dodaj wymaganie
          </Button>
        </div>
      </div>

      {/* Lista dni */}
      {refreshError && !loadError && (
        <Banner variant="warn">
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
            <span>Plan mógł się zmienić. {refreshError}</span>
            <Button size="sm" variant="ghost" onClick={() => load({ silent: true })}>Odśwież ponownie</Button>
          </div>
        </Banner>
      )}
      {loadError ? (
        <div role="alert">
          <Banner variant="danger">
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <span>Nie udało się wczytać planu obsady. {loadError}</span>
              <Button size="sm" variant="ghost" onClick={() => load()}>Spróbuj ponownie</Button>
            </div>
          </Banner>
        </div>
      ) : loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : dni.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted">Brak wymagań na ten tydzień. Dodaj je w formularzu poniżej.</Card>
      ) : (
        <div className="space-y-3" aria-busy={refreshing}>
          {dni.map(({ data, items }) => {
            const dObj = new Date(data)
            return (
              <details key={data} open className="card overflow-hidden">
                <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between p-4 font-semibold text-ink transition hover:bg-white/[0.03] [&::-webkit-details-marker]:hidden">
                  <span>
                    {NAZWY_DNI[dObj.getDay()]} <span className="text-muted">({ddmmyyyy(data)})</span>
                  </span>
                  <Icon name="chevronDown" className="h-4 w-4 text-muted" />
                </summary>
                <div className="space-y-3 border-t border-line p-4">
                  {items.map((w) => (
                    <WymRow
                      key={w.id}
                      w={w}
                      nazwa={stanMap[w.stanowisko_id]?.nazwa || '—'}
                      onSaved={upsertRequirement}
                      onDeleted={removeRequirement}
                      onRestored={upsertRequirement}
                      onBusyChange={setRowBusy}
                    />
                  ))}
                </div>
              </details>
            )
          })}
        </div>
      )}

      {/* Formularze */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* Zaplanuj zmianę */}
        <Card id="wymagania-dodaj" className="scroll-mt-24 p-6">
          <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-bold text-ink">
            <Icon name="plus" className="h-5 w-5 text-mint" /> Zaplanuj zmianę
          </h3>
          <div className="mx-auto max-w-md space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Data</span>
                <input
                  type="date"
                  min={s}
                  max={e}
                  value={form.data}
                  disabled={adding}
                  onChange={(event) => updateForm({ data: event.target.value })}
                  className="field"
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Stanowisko</span>
                <select
                  id="wymagania-stanowisko"
                  value={form.stanowisko}
                  disabled={adding}
                  onChange={(e) => {
                    updateForm({ stanowisko: e.target.value, podkategoria: '' })
                  }}
                  className="field"
                >
                  <option value="" className="bg-surface">Wybierz…</option>
                  {stanowiska.map((s) => (
                    <option key={s.id} value={s.id} className="bg-surface text-ink">{s.nazwa}</option>
                  ))}
                </select>
              </label>
            </div>

            {podkategorie.length > 0 && (
              <label className="flex flex-col gap-1.5 rounded-xl border border-info/20 bg-info/10 p-3">
                <span className="field-label flex items-center gap-1 text-info">
                  <Icon name="pin" className="h-3.5 w-3.5" /> Szablon rewiru
                </span>
                <select value={form.podkategoria} disabled={adding} onChange={(e) => onSubcat(e.target.value)} className="field">
                  <option value="" className="bg-surface">— Wpisz ręcznie —</option>
                  {podkategorie.map((pk) => (
                    <option key={pk.id} value={pk.id} className="bg-surface text-ink">
                      {pk.nazwa} ({pk.godz_od ? hhmm(pk.godz_od) : 'Brak'})
                    </option>
                  ))}
                </select>
              </label>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Przyjście</span>
                <input type="time" value={form.godzina} disabled={adding} onChange={(e) => updateForm({ godzina: e.target.value })} className="field" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Liczba osób</span>
                <input type="number" min="1" value={form.liczba} disabled={adding} onChange={(e) => updateForm({ liczba: e.target.value })} className="field text-center font-semibold" />
              </label>
            </div>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Rewir / strefa</span>
              <input value={form.rewir} disabled={adding} onChange={(e) => updateForm({ rewir: e.target.value })} placeholder="np. BarR1…" className="field" />
            </label>
            {addFeedback && (
              <div role={addFeedback.type === 'error' ? 'alert' : 'status'} aria-live="polite">
                {addFeedback.type === 'error'
                  ? <Banner variant="danger">{addFeedback.message} Dane pozostały w formularzu.</Banner>
                  : <p className="text-sm font-medium text-success">{addFeedback.message}</p>}
              </div>
            )}
            <Button
              className="w-full"
              onClick={dodaj}
              disabled={loading || !!loadError || refreshing || copying || rowBusyCount > 0}
              loading={adding}
              loadingLabel="Dodaję do planu…"
            >
              Dodaj do planu
            </Button>
          </div>
        </Card>

        {/* Kopiowanie tygodnia — przenosi cały tydzień na inny (dzień w dzień) */}
        <Card className="h-fit p-6">
          <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-bold text-ink">
            <Icon name="clipboard" className="h-5 w-5 text-info" /> Kopiuj tydzień
            <Hint>Przenieś wszystkie wymagania z jednego tygodnia na drugi (dzień w dzień).</Hint>
          </h3>
          <div className="mx-auto max-w-md space-y-4">
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Z tygodnia</span>
              <select
                value={kopFrom}
                disabled={copying}
                onChange={(e) => {
                  setKopFrom(e.target.value)
                  setCopyFeedback(null)
                }}
                className="field"
              >
                {tygodnie.opcje.map((o) => (
                  <option key={o.value} value={o.value} className="bg-surface text-ink">{o.label}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Na tydzień</span>
              <select
                value={kopTo}
                disabled={copying}
                onChange={(e) => {
                  setKopTo(e.target.value)
                  setCopyFeedback(null)
                }}
                className="field"
              >
                <option value="" className="bg-surface">Wybierz…</option>
                {tygodnie.opcje.map((o) => (
                  <option key={o.value} value={o.value} className="bg-surface text-ink">{o.label}</option>
                ))}
              </select>
            </label>
            {copyFeedback && (
              <div role={copyFeedback.type === 'error' ? 'alert' : 'status'} aria-live="polite">
                {copyFeedback.type === 'error'
                  ? <Banner variant="danger">{copyFeedback.message}</Banner>
                  : <p className="text-sm font-medium text-success">{copyFeedback.message}</p>}
              </div>
            )}
            <Button
              variant="ghost"
              className="w-full"
              onClick={kopiuj}
              disabled={loading || !!loadError || refreshing || adding || rowBusyCount > 0}
              loading={copying}
              loadingLabel="Kopiuję tydzień…"
            >
              <Icon name="clipboard" className="h-4 w-4" /> Kopiuj tydzień
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}
