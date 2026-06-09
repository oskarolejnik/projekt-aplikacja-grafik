import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Card } from '../ui/Card'
import { WeekSelect } from '../ui/WeekSelect'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { PillSwitch } from '../ui/PillSwitch'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm, ddmmyyyy, NAZWY_DNI, zakresDni, tloKoloru } from '../../lib/format'
import { motion, AnimatePresence } from 'framer-motion'

// Dyspozycyjność pracowników. Pracownicy zgłaszają się sami w swoim panelu, ale
// administrator może tu DOWOLNIE ustawić/zmienić/wyczyścić dyspozycję — klik w komórkę
// otwiera edytor (dostępny / niedostępny / od której godziny). Zapis: POST/DELETE /api/dyspozycje.
export default function Dyspozycje() {
  const { pracownicy, week, przyszly, setWeek, reloadDicts } = useData()
  const { toast } = useToast()

  // Na wejściu w Dyspozycyjność pokaż tydzień przyszły (składane z wyprzedzeniem).
  useEffect(() => {
    setWeek(przyszly)
  }, [przyszly, setWeek])
  const [dys, setDys] = useState([])
  const [loading, setLoading] = useState(true)
  const [edit, setEdit] = useState(null) // { prac, dt, dostepnosc, od, id }
  const [saving, setSaving] = useState(false)
  const reqId = useRef(0) // chroni przed wyścigiem ładowań przy zmianie tygodnia

  const [s, e] = week.split('|')
  const daty = useMemo(() => zakresDni(s, e), [s, e])

  const load = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    try {
      await reloadDicts()
      const d = await api(`/dyspozycje?start=${s}&end=${e}`)
      if (id !== reqId.current) return // starsze zapytanie (zmienił się tydzień) — pomiń
      setDys(d)
    } catch (err) {
      if (id === reqId.current) toast(err.message, 'error')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [s, e, reloadDicts, toast])

  useEffect(() => {
    load()
  }, [load])

  const map = useMemo(() => {
    const m = {}
    dys.forEach((d) => {
      m[`${d.data}_${d.pracownik_id}`] = d
    })
    return m
  }, [dys])

  const aktywni = pracownicy.filter((p) => p.aktywny)

  const otworz = (p, dt) => {
    const d = map[`${dt}_${p.id}`]
    setEdit({
      prac: p,
      dt,
      dostepnosc: d ? d.dostepnosc : true,
      od: d && d.godz_od ? hhmm(d.godz_od) : '',
      do: d && d.godz_do ? hhmm(d.godz_do) : '',
      id: d ? d.id : null,
    })
  }

  const zamknij = () => {
    if (!saving) setEdit(null)
  }

  const zapisz = async () => {
    setSaving(true)
    try {
      await api('/dyspozycje', 'POST', {
        pracownik_id: edit.prac.id,
        data: edit.dt,
        dostepnosc: edit.dostepnosc,
        godz_od: edit.dostepnosc && edit.od ? `${edit.od}:00` : null,
        godz_do: edit.dostepnosc && edit.do ? `${edit.do}:00` : null,
      })
      toast('Zapisano dyspozycyjność.', 'success')
      setEdit(null)
      await load()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const wyczysc = async () => {
    if (!edit.id) {
      setEdit(null)
      return
    }
    setSaving(true)
    try {
      await api(`/dyspozycje/${edit.id}`, 'DELETE')
      toast('Wyczyszczono dyspozycyjność.', 'success')
      setEdit(null)
      await load()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const calyDzien = edit ? !edit.od && !edit.do : true

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Dyspozycyjność pracowników</h2>
          <p className="mt-1 text-sm text-muted">Zgłoszenia z paneli pracowników — możesz je tu dowolnie zmieniać.</p>
        </div>
        <WeekSelect />
      </div>

      <Banner variant="info" className="mb-6">
        Kliknij dowolną komórkę, aby ustawić, zmienić lub wyczyścić dyspozycyjność pracownika na dany dzień.
      </Banner>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 min-w-[170px] border-b border-r border-line bg-surface-2 p-3 text-left text-xs font-bold uppercase tracking-wider text-muted">
                  Pracownik
                </th>
                {daty.map((dt) => {
                  const [, mm, dd] = dt.split('-')
                  const isW = [0, 6].includes(new Date(dt).getDay())
                  return (
                    <th key={dt} className={`min-w-[92px] border-b border-r border-line p-3 text-center text-xs font-bold ${isW ? 'text-blush' : 'text-ink'}`}>
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
                            onClick={() => otworz(p, dt)}
                            className={`flex h-full w-full items-center justify-center px-3 py-3 text-center text-xs font-semibold transition hover:bg-white/[0.05] ${cls}`}
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
              className="card relative z-10 w-full max-w-sm p-6"
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ duration: 0.3, ease: 'circOut' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-display text-lg font-bold text-ink">
                    {edit.prac.imie} {edit.prac.nazwisko}
                  </h3>
                  <p className="mt-0.5 text-sm capitalize text-muted">
                    {NAZWY_DNI[new Date(edit.dt).getDay()]}, {ddmmyyyy(edit.dt)}
                  </p>
                </div>
                <button onClick={zamknij} className="shrink-0 text-muted transition hover:text-ink" aria-label="Zamknij">
                  <Icon name="close" className="h-5 w-5" />
                </button>
              </div>

              <PillSwitch
                className="mt-5"
                value={edit.dostepnosc}
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
                    onClick={() => setEdit((st) => (calyDzien ? { ...st, od: '08:00', do: '' } : { ...st, od: '', do: '' }))}
                    className="flex items-center gap-2 self-start text-sm font-semibold text-muted transition active:scale-[0.97]"
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
                        value={edit.od}
                        onChange={(ev) => setEdit((st) => ({ ...st, od: ev.target.value }))}
                        className="field px-2 py-2"
                        style={{ width: '6.5rem' }}
                      />
                      <span>do</span>
                      <input
                        type="time"
                        value={edit.do}
                        onChange={(ev) => setEdit((st) => ({ ...st, do: ev.target.value }))}
                        className="field px-2 py-2"
                        style={{ width: '6.5rem' }}
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="mt-6 flex items-center justify-between gap-3">
                <button
                  onClick={wyczysc}
                  disabled={saving || !edit.id}
                  className="rounded-xl px-3 py-2 text-sm font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-30"
                >
                  Wyczyść
                </button>
                <div className="flex gap-3">
                  <button
                    onClick={zamknij}
                    disabled={saving}
                    className="rounded-xl border border-line bg-white/[0.04] px-4 py-2 text-sm font-semibold text-ink transition hover:bg-white/[0.09] active:scale-[0.97]"
                  >
                    Anuluj
                  </button>
                  <button
                    onClick={zapisz}
                    disabled={saving}
                    className="flex items-center gap-2 rounded-xl bg-cream px-4 py-2 text-sm font-bold text-bg shadow-cta transition hover:brightness-[1.03] active:scale-[0.97] disabled:opacity-60"
                  >
                    {saving ? <Spinner className="h-4 w-4" /> : <Icon name="check" className="h-4 w-4" />}
                    Zapisz
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </Card>
  )
}
