import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { WeekSelect } from '../ui/WeekSelect'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm, ddmmyyyy, NAZWY_DNI, zakresDni } from '../../lib/format'

// Podgląd OPUBLIKOWANEGO grafiku dla szefa — tylko do odczytu, pełny tydzień.
export default function SzefGrafik() {
  const { stanowiska, pracownicy, week, reloadDicts } = useData()
  const { toast } = useToast()
  const [przydzialy, setPrzydzialy] = useState([])
  const [pub, setPub] = useState({ opublikowany: false })
  const [loading, setLoading] = useState(true)

  const [s, e] = week.split('|')
  const dni = useMemo(() => zakresDni(s, e), [s, e])
  const stanMap = useMemo(() => Object.fromEntries(stanowiska.map((x) => [x.id, x.nazwa])), [stanowiska])
  const pracMap = useMemo(() => Object.fromEntries(pracownicy.map((p) => [p.id, `${p.imie} ${p.nazwisko}`])), [pracownicy])

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      await reloadDicts()
      const [pr, p] = await Promise.all([
        api(`/przydzialy?start=${s}&end=${e}`),
        api(`/grafik/publikacja?start=${s}&end=${e}`),
      ])
      setPrzydzialy(pr)
      setPub(p)
    } catch (err) {
      if (!silent) toast(err.message, 'error')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [s, e, reloadDicts, toast])

  useEffect(() => {
    load()
  }, [load])

  // Live: ciche odświeżanie co 20 s (tylko gdy karta widoczna).
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, 20000)
    return () => clearInterval(id)
  }, [load])

  const perDzien = useMemo(() => {
    const m = {}
    przydzialy.forEach((a) => {
      ;(m[a.data] = m[a.data] || []).push(a)
    })
    Object.values(m).forEach((arr) => arr.sort((x, y) => String(x.godz_od || '').localeCompare(String(y.godz_od || ''))))
    return m
  }, [przydzialy])

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Grafik</h2>
          <p className="mt-1 text-sm text-muted">Opublikowany grafik na wybrany tydzień (podgląd).</p>
        </div>
        <WeekSelect />
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : !pub.opublikowany ? (
        <Banner variant="warn">Grafik na ten tydzień nie został jeszcze opublikowany.</Banner>
      ) : (
        <div className="space-y-3">
          {dni.map((d) => {
            const zm = perDzien[d] || []
            const isW = [0, 6].includes(new Date(d).getDay())
            return (
              <div key={d} className="rounded-xl border border-line bg-white/[0.02] p-4">
                <div className="mb-2 flex items-baseline gap-2">
                  <span className={`font-semibold capitalize ${isW ? 'text-blush' : 'text-ink'}`}>{NAZWY_DNI[new Date(d).getDay()]}</span>
                  <span className="text-xs text-muted">{ddmmyyyy(d)}</span>
                  {zm.length > 0 && <span className="ml-auto text-xs text-muted">{zm.length} {zm.length === 1 ? 'zmiana' : 'zmian'}</span>}
                </div>
                {zm.length === 0 ? (
                  <div className="text-sm text-muted/50">—</div>
                ) : (
                  <div className="space-y-1.5">
                    {zm.map((a) => (
                      <div key={a.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                        <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 font-mono text-xs font-bold text-ink">
                          {a.godz_od ? hhmm(a.godz_od) : 'Cały dzień'}
                        </span>
                        <span className="font-semibold text-ink">{pracMap[a.pracownik_id] || '?'}</span>
                        <span className="text-muted">· {stanMap[a.stanowisko_id] || ''}</span>
                        {a.rewir && <span className="text-mint">({a.rewir})</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
