import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useData } from '../context/DataContext'
import { useToast } from '../components/ui/Toast'
import { WeekSelect } from '../components/ui/WeekSelect'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Banner } from '../components/ui/Banner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { ddmmyyyy, NAZWY_DNI } from '../lib/format'

// „Mój grafik" — pracownik widzi swoje zmiany TYLKO po udostępnieniu przez admina:
// dzień, godzina, stanowisko + rewir oraz z kim dzieli rewir.
export default function EmployeeSchedule({ onSeen }) {
  const { week, biezacy, setWeek } = useData()
  const { toast } = useToast()
  const [stan, setStan] = useState({ opublikowany: false, zmiany: [] })
  const [loading, setLoading] = useState(true)
  const reqId = useRef(0) // chroni przed wyścigiem ładowań przy zmianie tygodnia
  const [s, e] = week.split('|')

  // Na wejściu w „Mój grafik" pokaż tydzień bieżący.
  useEffect(() => {
    setWeek(biezacy)
  }, [biezacy, setWeek])

  const load = useCallback(async () => {
    const id = ++reqId.current
    setLoading(true)
    try {
      const r = await api(`/me/grafik?start=${s}&end=${e}`)
      if (id !== reqId.current) return // starsze zapytanie (zmienił się tydzień) — pomiń
      setStan(r)
      if (r.opublikowany && r.opublikowano_at && onSeen) onSeen(r.opublikowano_at)
    } catch (err) {
      if (id === reqId.current) toast(err.message, 'error')
    } finally {
      if (id === reqId.current) setLoading(false)
    }
  }, [s, e, toast, onSeen])

  useEffect(() => {
    load()
  }, [load])

  const dni = useMemo(() => {
    const m = {}
    stan.zmiany.forEach((z) => {
      ;(m[z.data] = m[z.data] || []).push(z)
    })
    return Object.keys(m)
      .sort()
      .map((d) => ({ data: d, zmiany: m[d] }))
  }, [stan])

  return (
    <>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <WeekSelect />
        <span className="text-sm text-muted">Twój grafik na wybrany tydzień.</span>
      </div>

      <Card className="p-6">
        {loading ? (
          <div className="grid place-items-center py-16">
            <Spinner className="h-6 w-6 text-muted" />
          </div>
        ) : !stan.opublikowany ? (
          <Banner variant="warn">
            Grafik na ten tydzień nie został jeszcze udostępniony przez administratora. Zajrzyj później.
          </Banner>
        ) : dni.length === 0 ? (
          <Banner variant="info">
            Grafik został udostępniony, ale w tym tygodniu nie masz przydzielonych zmian.
          </Banner>
        ) : (
          <div className="space-y-3">
            {dni.map(({ data, zmiany }, i) => (
              <div key={data} className="animate-fade-up rounded-xl border border-line bg-white/[0.02] p-4" style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
                <div className="mb-3 flex items-baseline gap-2">
                  <span className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(data).getDay()]}</span>
                  <span className="text-xs text-muted">{ddmmyyyy(data)}</span>
                </div>
                <div className="space-y-2">
                  {zmiany.map((z, i) => (
                    <div key={i} className={`rounded-lg border border-line border-l-[3px] bg-surface-2 p-3 ${z.zamyka ? 'border-l-lemon' : 'border-l-mint'}`}>
                      <div className="flex flex-wrap items-center gap-2">
                        {z.godz_od && (
                          <span className="rounded-md bg-white/[0.06] px-2 py-0.5 font-mono text-sm font-bold text-ink">{z.godz_od}</span>
                        )}
                        <span className="font-bold text-ink">{z.stanowisko}</span>
                        {z.rewir && <span className="text-sm font-semibold text-mint">{z.rewir}</span>}
                        {z.zamyka && (
                          <span className="inline-flex items-center gap-1 rounded-md bg-lemon/15 px-2 py-0.5 text-xs font-bold text-lemon">
                            <Icon name="key" className="h-3 w-3" /> Zamykasz
                          </span>
                        )}
                      </div>
                      {z.wspolpracownicy.length > 0 && (
                        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                          <Icon name="users" className="h-3.5 w-3.5" />
                          <span className="font-semibold text-ink/80">Z kim:</span>
                          {z.wspolpracownicy.map((w, j) => {
                            const innaStan = w.stanowisko && w.stanowisko !== z.stanowisko
                            return (
                              <span key={j} className={w.zamyka ? 'font-semibold text-lemon' : ''}>
                                {innaStan && <span className="text-ink/50">{w.stanowisko}: </span>}
                                {w.imie}
                                {(w.godz_od || w.zamyka) && ` (${[w.godz_od, w.zamyka ? 'zamyka' : ''].filter(Boolean).join(', ')})`}
                                {j < z.wspolpracownicy.length - 1 ? ',' : ''}
                              </span>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  )
}
