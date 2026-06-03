import { useState, useEffect, useCallback, useMemo } from 'react'
import { Card } from '../ui/Card'
import { WeekSelect } from '../ui/WeekSelect'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm, zakresDni } from '../../lib/format'

// Podgląd dyspozycyjności zgłoszonej przez pracowników (zastępuje import CSV).
// Pracownicy zgłaszają się sami w swoim panelu; admin widzi tu zbiorcze zestawienie.
export default function Dyspozycje() {
  const { pracownicy, week, reloadDicts } = useData()
  const { toast } = useToast()
  const [dys, setDys] = useState([])
  const [loading, setLoading] = useState(true)

  const [s, e] = week.split('|')
  const daty = useMemo(() => zakresDni(s, e), [s, e])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      await reloadDicts()
      setDys(await api(`/dyspozycje?start=${s}&end=${e}`))
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
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

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Dyspozycyjność pracowników</h2>
          <p className="mt-1 text-sm text-muted">Zgłoszenia z paneli pracowników na wybrany tydzień.</p>
        </div>
        <WeekSelect />
      </div>

      <Banner variant="info" className="mb-6">
        Pracownicy zgłaszają dyspozycyjność samodzielnie po zalogowaniu. Ten widok służy tylko do podglądu.
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
                    <td className="sticky left-0 z-10 border-b border-r border-line bg-bg-2 p-3 font-semibold text-ink">
                      {p.imie} {p.nazwisko}
                    </td>
                    {daty.map((dt) => {
                      const d = map[`${dt}_${p.id}`]
                      let cls = 'text-muted/40'
                      let txt = '—'
                      if (d) {
                        if (d.dostepnosc) {
                          cls = 'text-success'
                          txt = d.godz_od ? `od ${hhmm(d.godz_od)}` : 'tak'
                        } else {
                          cls = 'text-danger'
                          txt = 'nie'
                        }
                      }
                      return (
                        <td key={dt} className={`border-b border-r border-line p-3 text-center text-xs font-semibold ${cls}`}>
                          {txt}
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
    </Card>
  )
}
