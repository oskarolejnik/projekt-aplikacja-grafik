import { useState, useEffect, useCallback, useMemo } from 'react'
import { useData } from '../context/DataContext'
import { useToast } from '../components/ui/Toast'
import { WeekSelect } from '../components/ui/WeekSelect'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { ddmmyyyy, hhmm, NAZWY_DNI, zakresDni } from '../lib/format'

// Godzina imprezy z arkusza bywa łańcuchem ("14:30:00", "Brak", "None"...).
const fmtGodzina = (g) => {
  if (!g || g === 'None' || g === 'Brak') return ''
  const m = String(g).match(/^(\d{1,2}):(\d{2})/)
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : String(g)
}

// Treść widoku „Moja dyspozycyjność" (nagłówek/powłokę dostarcza EmployeeArea).
// Przy każdym dniu pokazujemy imprezy z bazy, by pracownik dopasował godziny.
export default function EmployeeAvailability() {
  const { week } = useData()
  const { toast } = useToast()
  const [dni, setDni] = useState([])
  const [imprezyMap, setImprezyMap] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [s, e] = week.split('|')
  const daty = useMemo(() => zakresDni(s, e), [s, e])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [existing, imprezy] = await Promise.all([
        api(`/me/dyspozycje?start=${s}&end=${e}`),
        api(`/me/imprezy?start=${s}&end=${e}`),
      ])
      const map = Object.fromEntries(existing.map((d) => [d.data, d]))
      setDni(
        daty.map((d) => {
          const rec = map[d]
          return {
            data: d,
            dostepnosc: rec ? rec.dostepnosc : true, // domyślnie dostępny
            od: rec && rec.godz_od ? hhmm(rec.godz_od) : '',
          }
        }),
      )
      const im = {}
      imprezy.forEach((x) => {
        ;(im[x.data] = im[x.data] || []).push(x)
      })
      setImprezyMap(im)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [s, e, daty, toast])

  useEffect(() => {
    load()
  }, [load])

  const setDay = (idx, patch) => setDni((cur) => cur.map((d, i) => (i === idx ? { ...d, ...patch } : d)))

  const zapisz = async () => {
    setSaving(true)
    try {
      await api('/me/dyspozycje', 'PUT', {
        dyspozycje: dni.map((d) => ({
          data: d.data,
          dostepnosc: d.dostepnosc,
          godz_od: d.dostepnosc && d.od ? `${d.od}:00` : null,
        })),
      })
      toast('Zapisano Twoją dyspozycyjność.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <WeekSelect />
        <span className="text-sm text-muted">Zaznacz dni i godziny, w których możesz pracować.</span>
      </div>

      <Card className="p-6">
        {loading ? (
          <div className="grid place-items-center py-16">
            <Spinner className="h-6 w-6 text-muted" />
          </div>
        ) : (
          <div className="space-y-3">
            {dni.map((d, i) => {
              const imprezy = imprezyMap[d.data] || []
              return (
                <div key={d.data} className="rounded-xl border border-line bg-white/[0.02] p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-[150px]">
                      <div className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(d.data).getDay()]}</div>
                      <div className="text-xs text-muted">{ddmmyyyy(d.data)}</div>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="flex overflow-hidden rounded-lg border border-line">
                        <button
                          onClick={() => setDay(i, { dostepnosc: true })}
                          className={`px-4 py-2 text-xs font-bold transition ${d.dostepnosc ? 'bg-success text-bg' : 'text-muted hover:text-ink'}`}
                        >
                          Dostępny
                        </button>
                        <button
                          onClick={() => setDay(i, { dostepnosc: false })}
                          className={`px-4 py-2 text-xs font-bold transition ${!d.dostepnosc ? 'bg-danger text-white' : 'text-muted hover:text-ink'}`}
                        >
                          Niedostępny
                        </button>
                      </div>

                      <label className="flex items-center gap-2 text-xs text-muted">
                        <span className="hidden sm:inline">od</span>
                        <input
                          type="time"
                          value={d.od}
                          onChange={(ev) => setDay(i, { od: ev.target.value })}
                          disabled={!d.dostepnosc}
                          className="field w-28 px-2 py-2 disabled:opacity-40"
                        />
                      </label>
                    </div>
                  </div>

                  {imprezy.length > 0 && (
                    <div className="mt-3 space-y-1.5 border-t border-line pt-3">
                      <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-blush">
                        <Icon name="calendar" className="h-3.5 w-3.5" /> Imprezy tego dnia
                      </div>
                      {imprezy.map((imp) => (
                        <div key={imp.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 pl-5 text-xs">
                          <span className="font-semibold text-ink">{imp.klient}</span>
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

        <button
          onClick={zapisz}
          disabled={saving || loading}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-cream px-6 py-3.5 text-sm font-bold uppercase tracking-[0.15em] text-bg shadow-cta transition hover:brightness-[1.03] active:scale-[0.98] disabled:opacity-60"
        >
          {saving ? <Spinner className="h-4 w-4" /> : <Icon name="check" className="h-4 w-4" />}
          {saving ? 'Zapisywanie…' : 'Zapisz dyspozycyjność'}
        </button>
      </Card>
    </>
  )
}
