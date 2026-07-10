import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { WeekSelect } from '../ui/WeekSelect'
import { Spinner } from '../ui/Spinner'
import { PillSwitch } from '../ui/PillSwitch'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm, ddmmyyyy, NAZWY_DNI, zakresDni, tloKoloru } from '../../lib/format'
import { motion, AnimatePresence } from 'framer-motion'

const editSnapshot = (edit) => JSON.stringify({
  dostepnosc: !!edit?.dostepnosc,
  od: edit?.od || '',
  do: edit?.do || '',
})

// Dyspozycyjność pracowników. Pracownicy zgłaszają się sami w swoim panelu, ale
// administrator może tu DOWOLNIE ustawić/zmienić/wyczyścić dyspozycję — klik w komórkę
// otwiera edytor (dostępny / niedostępny / od której godziny). Zapis: POST/DELETE /api/dyspozycje.
export default function Dyspozycje({ active = true }) {
  const { pracownicy, week, przyszly, setWeek, reloadDicts } = useData()
  const { toast, confirm } = useToast()
  const ustawionoPrzyszly = useRef(false)

  // Na wejściu w Dyspozycyjność pokaż tydzień przyszły (składane z wyprzedzeniem).
  useEffect(() => {
    if (!active || ustawionoPrzyszly.current) return
    ustawionoPrzyszly.current = true
    setWeek(przyszly)
  }, [active, przyszly, setWeek])
  const [dys, setDys] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [edit, setEdit] = useState(null) // { prac, dt, dostepnosc, od, do, id, originalSnapshot }
  const [modalAction, setModalAction] = useState(null) // 'save' | 'clear'
  const [modalError, setModalError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const reqId = useRef(0) // chroni przed wyścigiem ładowań przy zmianie tygodnia
  const triggerRef = useRef(null)

  const [s, e] = week.split('|')
  const rangeRef = useRef({ s, e })
  rangeRef.current = { s, e }
  const daty = useMemo(() => zakresDni(s, e), [s, e])

  const load = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    setLoadError(null)
    setLastUpdate(null)
    try {
      await reloadDicts()
      const d = await api(`/dyspozycje?start=${s}&end=${e}`)
      if (id !== reqId.current) return // starsze zapytanie (zmienił się tydzień) — pomiń
      setDys(d)
    } catch (err) {
      if (id === reqId.current) setLoadError(err.message || 'Nie udało się wczytać dyspozycyjności.')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [s, e, reloadDicts])

  useEffect(() => {
    if (active) load()
  }, [active, load])

  const map = useMemo(() => {
    const m = {}
    dys.forEach((d) => {
      m[`${d.data}_${d.pracownik_id}`] = d
    })
    return m
  }, [dys])

  const aktywni = pracownicy.filter((p) => p.aktywny)

  const otworz = (p, dt, trigger) => {
    const d = map[`${dt}_${p.id}`]
    const nextEdit = {
      prac: p,
      dt,
      dostepnosc: d ? d.dostepnosc : true,
      od: d && d.godz_od ? hhmm(d.godz_od) : '',
      do: d && d.godz_do ? hhmm(d.godz_do) : '',
      id: d ? d.id : null,
    }
    triggerRef.current = trigger
    setModalError(null)
    setEdit({
      ...nextEdit,
      original: { dostepnosc: nextEdit.dostepnosc, od: nextEdit.od, do: nextEdit.do },
      originalSnapshot: editSnapshot(nextEdit),
    })
  }

  const restoreFocus = () => {
    const trigger = triggerRef.current
    setTimeout(() => trigger?.focus(), 0)
  }

  const zamknij = async () => {
    if (modalAction || !edit) return
    if (editSnapshot(edit) !== edit.originalSnapshot) {
      const discard = await confirm('Odrzucić niezapisane zmiany w tej dyspozycyjności?', {
        title: 'Niezapisane zmiany',
        confirmText: 'Odrzuć zmiany',
      })
      if (!discard) return
    }
    setEdit(null)
    setModalError(null)
    restoreFocus()
  }

  const upsertAvailability = useCallback((saved) => {
    setDys((current) => {
      const withoutSaved = current.filter((item) => item.id !== saved.id && !(item.pracownik_id === saved.pracownik_id && item.data === saved.data))
      const { s: currentStart, e: currentEnd } = rangeRef.current
      return saved.data >= currentStart && saved.data <= currentEnd ? [...withoutSaved, saved] : withoutSaved
    })
  }, [])

  const zapisz = async () => {
    if (modalAction || !edit) return
    setModalAction('save')
    setModalError(null)
    try {
      const saved = await api('/dyspozycje', 'POST', {
        pracownik_id: edit.prac.id,
        data: edit.dt,
        dostepnosc: edit.dostepnosc,
        godz_od: edit.dostepnosc && edit.od ? `${edit.od}:00` : null,
        godz_do: edit.dostepnosc && edit.do ? `${edit.do}:00` : null,
      })
      upsertAvailability(saved)
      setLastUpdate(`Zapisano: ${edit.prac.imie} ${edit.prac.nazwisko}, ${ddmmyyyy(edit.dt)}.`)
      setEdit(null)
      restoreFocus()
    } catch (err) {
      setModalError(err.message || 'Nie udało się zapisać dyspozycyjności.')
    } finally {
      setModalAction(null)
    }
  }

  const wyczysc = async () => {
    if (modalAction || !edit) return
    if (!edit.id) {
      setEdit(null)
      restoreFocus()
      return
    }
    const removed = {
      pracownik_id: edit.prac.id,
      data: edit.dt,
      dostepnosc: edit.original?.dostepnosc ?? edit.dostepnosc,
      godz_od: edit.original?.od ? `${edit.original.od}:00` : null,
      godz_do: edit.original?.do ? `${edit.original.do}:00` : null,
    }
    setModalAction('clear')
    setModalError(null)
    try {
      await api(`/dyspozycje/${edit.id}`, 'DELETE')
      setDys((current) => current.filter((item) => item.id !== edit.id))
      const label = `${edit.prac.imie} ${edit.prac.nazwisko}, ${ddmmyyyy(edit.dt)}`
      setLastUpdate(`Wyczyszczono: ${label}.`)
      setEdit(null)
      restoreFocus()
      toast(`Wyczyszczono dyspozycyjność: ${label}.`, 'info', {
        action: {
          label: 'Cofnij',
          onClick: async () => {
            try {
              const restored = await api('/dyspozycje', 'POST', removed)
              upsertAvailability(restored)
              setLastUpdate(`Przywrócono: ${label}.`)
              toast('Przywrócono dyspozycyjność.', 'success')
            } catch (error) {
              toast(error.message || 'Nie udało się przywrócić dyspozycyjności.', 'error')
            }
          },
        },
      })
    } catch (err) {
      setModalError(err.message || 'Nie udało się wyczyścić dyspozycyjności.')
    } finally {
      setModalAction(null)
    }
  }

  const calyDzien = edit ? !edit.od && !edit.do : true
  const editDirty = !!edit && editSnapshot(edit) !== edit.originalSnapshot
  const canSave = !!edit && (!edit.id || editDirty)

  return (
    <Card className="p-6 md:p-8">
      <SectionHeader title="Dyspozycyjność pracowników"
        subtitle="Zgłoszenia z paneli pracowników — możesz je tu dowolnie zmieniać. Kliknij dowolną komórkę, aby ustawić, zmienić lub wyczyścić dyspozycyjność na dany dzień.">
        {lastUpdate && <span className="text-xs font-medium text-success" role="status" aria-live="polite">{lastUpdate}</span>}
        <WeekSelect disabled={loading || !!modalAction} />
      </SectionHeader>

      {loadError ? (
        <div role="alert">
          <Banner variant="danger">
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <span>Nie udało się wczytać dyspozycyjności. {loadError}</span>
              <Button size="sm" variant="ghost" onClick={load}>Spróbuj ponownie</Button>
            </div>
          </Banner>
        </div>
      ) : loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line" aria-busy={!!modalAction}>
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 min-w-[170px] border-b border-r border-line bg-surface-2 p-3 text-left text-xs font-bold uppercase tracking-wider text-muted">
                  Pracownik
                </th>
                {daty.map((dt) => {
                  const [, mm, dd] = dt.split('-')
                  const dayIndex = new Date(dt).getDay()
                  const isW = [0, 6].includes(dayIndex)
                  return (
                    <th key={dt} className={`min-w-[92px] border-b border-r border-line p-3 text-center text-xs font-semibold ${isW ? 'text-blush' : 'text-ink'}`}>
                      <span className="block text-[10px] capitalize text-muted">{NAZWY_DNI[dayIndex]}</span>
                      {dd}.{mm}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {aktywni.length === 0 ? (
                <tr>
                  <td colSpan={daty.length + 1} className="p-10 text-center text-muted">Brak aktywnych pracowników.</td>
                </tr>
              ) : (
                aktywni.map((p) => (
                  <tr key={p.id}>
                    <td className="sticky left-0 z-10 border-b border-r border-line bg-bg-2 p-3 font-semibold text-ink" style={{ background: tloKoloru(p.kolor) }}>
                      {p.imie} {p.nazwisko}
                    </td>
                    {daty.map((dt) => {
                      const d = map[`${dt}_${p.id}`]
                      let cls = 'text-muted/40'
                      let txt = '—'
                      if (d) {
                        if (d.dostepnosc) {
                          cls = 'text-success'
                          const o = d.godz_od ? hhmm(d.godz_od) : ''
                          const dd = d.godz_do ? hhmm(d.godz_do) : ''
                          txt = o && dd ? `${o}–${dd}` : o ? `od ${o}` : dd ? `do ${dd}` : 'tak'
                        } else {
                          cls = 'text-danger'
                          txt = 'nie'
                        }
                      }
                      return (
                        <td key={dt} className="border-b border-r border-line p-0">
                          <button
                            type="button"
                            onClick={(event) => otworz(p, dt, event.currentTarget)}
                            aria-label={`${p.imie} ${p.nazwisko}, ${NAZWY_DNI[new Date(dt).getDay()]} ${ddmmyyyy(dt)}: ${d ? (d.dostepnosc ? `dostępny ${txt}` : 'niedostępny') : 'brak zgłoszenia'}`}
                            className={`flex min-h-11 w-full items-center justify-center px-3 py-3 text-center text-xs font-semibold transition hover:bg-white/[0.05] ${cls}`}
                            style={{ WebkitTapHighlightColor: 'transparent' }}
                          >
                            {txt}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Edytor dyspozycji (modal) — styl spójny z confirm() z Toast.jsx. */}
      <AnimatePresence>
        {edit && (
          <div className="fixed inset-0 z-[1100] grid place-items-center p-4">
            <motion.div
              className="absolute inset-0 bg-black/60 backdrop-blur-md"
              onClick={zamknij}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25, ease: 'circOut' }}
            />
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-labelledby="availability-editor-title"
              className="material relative z-10 w-full max-w-md p-6"
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ duration: 0.3, ease: 'circOut' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 id="availability-editor-title" className="font-display text-lg font-semibold text-ink">
                    {edit.prac.imie} {edit.prac.nazwisko}
                  </h3>
                  <p className="mt-0.5 text-sm capitalize text-muted">
                    {NAZWY_DNI[new Date(edit.dt).getDay()]}, {ddmmyyyy(edit.dt)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={zamknij}
                  disabled={!!modalAction}
                  className="grid min-h-11 min-w-11 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-white/[0.06] hover:text-ink disabled:cursor-wait disabled:opacity-50"
                  aria-label="Zamknij edycję dyspozycyjności"
                >
                  <Icon name="close" className="h-5 w-5" />
                </button>
              </div>

              <PillSwitch
                className="mt-5"
                value={edit.dostepnosc}
                disabled={!!modalAction}
                onChange={(v) => setEdit((st) => ({ ...st, dostepnosc: v }))}
                options={[
                  { value: true, label: 'Dostępny', activeBg: 'bg-success', activeText: 'text-bg' },
                  { value: false, label: 'Niedostępny', activeBg: 'bg-danger', activeText: 'text-white' },
                ]}
              />

              {edit.dostepnosc && (
                <div className="mt-4 flex flex-col gap-3 rounded-xl border border-line bg-white/[0.02] p-3">
                  <button
                    type="button"
                    role="switch"
                    aria-checked={calyDzien}
                    disabled={!!modalAction}
                    onClick={() => setEdit((st) => (calyDzien ? { ...st, od: '08:00', do: '' } : { ...st, od: '', do: '' }))}
                    className="flex items-center gap-2 self-start text-sm font-semibold text-muted transition active:scale-[0.98]"
                    style={{ WebkitTapHighlightColor: 'transparent' }}
                  >
                    <span className={`relative inline-flex h-6 w-11 items-center rounded-full px-0.5 transition-colors duration-200 ${calyDzien ? 'bg-success' : 'bg-white/15'}`}>
                      <span
                        className="h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200"
                        style={{ transform: `translateX(${calyDzien ? 20 : 0}px)` }}
                      />
                    </span>
                    Cały dzień
                  </button>
                  {!calyDzien && (
                    <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
                      <span>od</span>
                      <input
                        type="time"
                        aria-label="Dostępny od"
                        value={edit.od}
                        disabled={!!modalAction}
                        onChange={(ev) => setEdit((st) => ({ ...st, od: ev.target.value }))}
                        className="field px-2 py-2"
                        style={{ width: '6.5rem' }}
                      />
                      <span>do</span>
                      <input
                        type="time"
                        aria-label="Dostępny do"
                        value={edit.do}
                        disabled={!!modalAction}
                        onChange={(ev) => setEdit((st) => ({ ...st, do: ev.target.value }))}
                        className="field px-2 py-2"
                        style={{ width: '6.5rem' }}
                      />
                    </div>
                  )}
                </div>
              )}

              {modalError && (
                <div className="mt-4" role="alert">
                  <Banner variant="danger">{modalError} Dane pozostały w edytorze.</Banner>
                </div>
              )}

              <div className="mt-4 min-h-5 text-xs" role="status" aria-live="polite">
                {modalAction
                  ? <span className="text-muted">{modalAction === 'save' ? 'Zapisuję zmianę…' : 'Czyszczę zgłoszenie…'}</span>
                  : editDirty
                    ? <span className="text-lemon">Masz niezapisane zmiany.</span>
                    : <span className="text-muted">{edit.id ? 'Brak niezapisanych zmian.' : 'Nowe zgłoszenie — wybierz stan i zapisz.'}</span>}
              </div>

              <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
                <Button
                  variant="subtle"
                  size="sm"
                  onClick={wyczysc}
                  disabled={!!modalAction || !edit.id}
                  loading={modalAction === 'clear'}
                  loadingLabel="Czyszczę…"
                  className="text-danger hover:bg-danger/10"
                  aria-label="Wyczyść zgłoszenie dyspozycyjności"
                >
                  Wyczyść
                </Button>
                <div className="flex gap-3">
                  <Button
                    variant="ghost"
                    onClick={zamknij}
                    disabled={!!modalAction}
                  >
                    Anuluj
                  </Button>
                  <Button
                    onClick={zapisz}
                    disabled={!!modalAction || !canSave}
                    loading={modalAction === 'save'}
                    loadingLabel="Zapisuję…"
                  >
                    <Icon name="check" className="h-4 w-4" />
                    {modalError ? 'Ponów zapis' : 'Zapisz'}
                  </Button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </Card>
  )
}
