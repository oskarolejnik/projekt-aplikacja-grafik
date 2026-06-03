import { useEffect, useState, useCallback, useMemo } from 'react'
import { Button } from '../ui/Button'
import { WeekSelect } from '../ui/WeekSelect'
import { Banner } from '../ui/Banner'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { hhmm, zakresDni } from '../../lib/format'

// Interaktywny grafik: pracownicy × dni. Status dyspozycji, przydziały zmian,
// dodawanie z szablonów wymagań, auto-przydział i czyszczenie. Logika map 1:1
// z poprzednią aplikacją.
export default function Grafik() {
  const { stanowiska, pracownicy, week, reloadDicts } = useData()
  const { toast, confirm } = useToast()
  const [przydzialy, setPrzydzialy] = useState([])
  const [dyspozycje, setDyspozycje] = useState([])
  const [wymagania, setWymagania] = useState([])
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState(false)

  const load = useCallback(async () => {
    const [s, e] = week.split('|')
    setLoading(true)
    try {
      await reloadDicts()
      const [pr, dy, wy] = await Promise.all([
        api(`/przydzialy?start=${s}&end=${e}`),
        api(`/dyspozycje?start=${s}&end=${e}`),
        api(`/wymagania?start=${s}&end=${e}`),
      ])
      setPrzydzialy(pr)
      setDyspozycje(dy)
      setWymagania(wy)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [week, reloadDicts, toast])

  useEffect(() => {
    load()
  }, [load])

  const [s, e] = week.split('|')
  const dates = useMemo(() => zakresDni(s, e), [s, e])
  const stanMap = useMemo(() => Object.fromEntries(stanowiska.map((x) => [x.id, x])), [stanowiska])

  const przyMap = useMemo(() => {
    const m = {}
    przydzialy.forEach((a) => {
      const k = `${a.data}_${a.pracownik_id}`
      ;(m[k] = m[k] || []).push(a)
    })
    return m
  }, [przydzialy])

  const dysMap = useMemo(() => {
    const m = {}
    dyspozycje.forEach((d) => {
      m[`${d.data}_${d.pracownik_id}`] = d
    })
    return m
  }, [dyspozycje])

  const wymMap = useMemo(() => {
    const m = {}
    wymagania.forEach((w) => {
      ;(m[w.data] = m[w.data] || []).push(w)
    })
    return m
  }, [wymagania])

  // Szablony (wymagania) dostępne dla danego pracownika w danym dniu.
  const szablonyDla = useCallback(
    (dt, p) => {
      const isW = [0, 6].includes(new Date(dt).getDay())
      const kwalIds = new Set((p.kwalifikacje || []).map((k) => k.id))
      return (wymMap[dt] || []).filter((w) => {
        const stan = stanMap[w.stanowisko_id]
        return stan && (!stan.tylko_weekend || isW) && kwalIds.has(w.stanowisko_id)
      })
    },
    [wymMap, stanMap],
  )

  const dodajPrzydzial = async (dt, pId, w) => {
    try {
      await api('/przydzialy', 'POST', { data: dt, stanowisko_id: w.stanowisko_id, pracownik_id: pId, godz_od: w.godz_od })
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }
  const usunPrzydzial = async (aid) => {
    try {
      await api(`/przydzialy/${aid}`, 'DELETE')
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const autoAssign = async () => {
    setProcessing(true)
    try {
      await api(`/auto-assign?start=${s}&end=${e}`, 'POST')
      await load()
      toast('Auto-przydział zakończony.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setProcessing(false)
    }
  }
  const wyczysc = async () => {
    if (!(await confirm('Wyczyścić cały grafik dla tego tygodnia?'))) return
    try {
      await api(`/przydzialy?start=${s}&end=${e}`, 'DELETE')
      load()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const aktywni = pracownicy.filter((p) => p.aktywny)

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <WeekSelect />
        <div className="flex flex-wrap gap-3">
          <Button variant="success" onClick={autoAssign} disabled={processing}>
            {processing ? <Spinner className="h-4 w-4" /> : <Icon name="robot" className="h-5 w-5" />}
            Auto-przydział AI
          </Button>
          <Button variant="ghost" onClick={wyczysc} className="text-danger hover:bg-danger/10">
            Wyczyść tabelę
          </Button>
        </div>
      </div>

      {processing && <Banner variant="info">Trwa procesowanie algorytmu auto-przydziału…</Banner>}

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                <th className="sticky left-0 z-20 min-w-[180px] border-b border-r border-line bg-surface-2 p-4 text-left text-xs font-bold uppercase tracking-wider text-muted">
                  Pracownik
                </th>
                {dates.map((dt) => {
                  const [, mm, dd] = dt.split('-')
                  const isW = [0, 6].includes(new Date(dt).getDay())
                  return (
                    <th
                      key={dt}
                      className={`min-w-[150px] border-b border-r border-line p-4 text-center text-sm font-bold ${isW ? 'text-blush' : 'text-ink'}`}
                    >
                      {dd}.{mm}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {aktywni.length === 0 ? (
                <tr>
                  <td colSpan={dates.length + 1} className="p-10 text-center text-sm text-muted">
                    Brak aktywnych pracowników.
                  </td>
                </tr>
              ) : (
                aktywni.map((p) => (
                  <tr key={p.id} className="group">
                    <td className="sticky left-0 z-10 border-b border-r border-line bg-bg-2 p-4 font-bold text-ink shadow-[2px_0_8px_rgba(0,0,0,0.25)]">
                      {p.imie} {p.nazwisko}
                    </td>
                    {dates.map((dt) => {
                      const dys = dysMap[`${dt}_${p.id}`]
                      const pAt = przyMap[`${dt}_${p.id}`] || []
                      const szablony = szablonyDla(dt, p)

                      const status = dys
                        ? dys.dostepnosc
                          ? dys.godz_od
                            ? `Od ${hhmm(dys.godz_od)}`
                            : 'Dostępny'
                          : 'Niedostępny'
                        : 'brak'
                      const cellBg = !dys ? 'bg-white/[0.01]' : dys.dostepnosc ? 'bg-success/[0.04]' : 'bg-danger/[0.04]'
                      const statusColor = !dys
                        ? 'text-muted border-line'
                        : dys.dostepnosc
                          ? 'text-success border-success/30 bg-success/10'
                          : 'text-danger border-danger/30 bg-danger/10'

                      return (
                        <td key={dt} className={`border-b border-r border-line p-3 align-top ${cellBg}`}>
                          <div className={`mx-auto mb-2 w-fit rounded-md border px-2 py-0.5 text-center text-[10px] font-bold ${statusColor}`}>
                            {status}
                          </div>
                          <div className="flex flex-col gap-2">
                            {pAt.map((a) => {
                              const stan = stanMap[a.stanowisko_id]
                              const szab = szablony.find((w) => w.stanowisko_id === a.stanowisko_id && w.godz_od === a.godz_od)
                              return (
                                <div key={a.id} className="rounded-lg border border-line border-l-[3px] border-l-mint bg-surface-2 p-2 text-left text-xs">
                                  <div className="flex items-start justify-between gap-1">
                                    <span className="font-bold text-ink">
                                      {stan?.nazwa}
                                      {szab?.rewir && <span className="text-mint"> ({szab.rewir})</span>}
                                    </span>
                                    <button
                                      onClick={() => usunPrzydzial(a.id)}
                                      className="shrink-0 text-muted transition hover:text-danger"
                                      aria-label="Anuluj zmianę"
                                    >
                                      <Icon name="close" className="h-3.5 w-3.5" />
                                    </button>
                                  </div>
                                  <span className="mt-1 flex items-center gap-1 font-mono text-[10px] text-muted">
                                    <Icon name="clock" className="h-3 w-3" /> {a.godz_od ? hhmm(a.godz_od) : 'Dowolnie'}
                                  </span>
                                </div>
                              )
                            })}

                            {dys?.dostepnosc && szablony.length > 0 && (
                              <select
                                value=""
                                onChange={(ev) => {
                                  const idx = ev.target.value
                                  if (idx === '') return
                                  dodajPrzydzial(dt, p.id, szablony[+idx])
                                }}
                                className="w-full cursor-pointer rounded-lg border border-dashed border-line bg-surface-2 p-1.5 text-center text-xs font-medium text-mint outline-none transition hover:border-mint/50"
                              >
                                <option value="" className="bg-surface text-muted">+ Dodaj</option>
                                {szablony.map((w, i) => (
                                  <option key={i} value={i} className="bg-surface text-ink">
                                    {stanMap[w.stanowisko_id].nazwa}
                                    {w.rewir ? ` (${w.rewir})` : ''}
                                    {w.godz_od ? ` [${hhmm(w.godz_od)}]` : ''}
                                  </option>
                                ))}
                              </select>
                            )}
                          </div>
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
    </div>
  )
}
