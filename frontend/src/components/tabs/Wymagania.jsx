import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { WeekSelect } from '../ui/WeekSelect'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, hhmm, NAZWY_DNI } from '../../lib/format'

// Pojedyncze wymaganie w karcie dnia — edycja liczby osób (zapis na blur).
function WymRow({ w, nazwa, onChanged }) {
  const { toast, confirm } = useToast()
  const [liczba, setLiczba] = useState(w.liczba_osob)

  const save = async () => {
    if (+liczba === w.liczba_osob || liczba === '') return
    try {
      await api('/wymagania', 'POST', { ...w, liczba_osob: +liczba })
      onChanged()
    } catch (e) {
      toast(e.message, 'error')
    }
  }
  const usun = async () => {
    if (!(await confirm('Usunąć to wymaganie?'))) return
    try {
      await api(`/wymagania/${w.id}`, 'DELETE')
      onChanged()
    } catch (e) {
      toast(e.message, 'error')
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
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase text-muted">Osób</span>
          <input
            type="number"
            min="1"
            value={liczba}
            onChange={(e) => setLiczba(e.target.value)}
            onBlur={save}
            className="field w-16 px-2 py-2 text-center text-lg font-bold"
          />
        </div>
        <button onClick={usun} className="rounded-lg border border-danger/20 bg-danger/10 p-2 text-danger transition hover:bg-danger/20" aria-label="Usuń wymaganie">
          <Icon name="trash" className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

export default function Wymagania() {
  const { stanowiska, week, reloadDicts } = useData()
  const { toast } = useToast()
  const [wymagania, setWymagania] = useState([])
  const [loading, setLoading] = useState(true)

  // Formularz dodawania
  const dzis = new Date().toISOString().slice(0, 10)
  const [fData, setFData] = useState(dzis)
  const [fStan, setFStan] = useState('')
  const [fSubcat, setFSubcat] = useState('')
  const [fOd, setFOd] = useState('')
  const [fLiczba, setFLiczba] = useState(1)
  const [fRewir, setFRewir] = useState('')

  // Formularz kopiowania
  const [kopSource, setKopSource] = useState(dzis)
  const [kopStart, setKopStart] = useState('')
  const [kopEnd, setKopEnd] = useState('')

  const stanMap = useMemo(() => Object.fromEntries(stanowiska.map((s) => [s.id, s])), [stanowiska])
  const wybraneStan = stanMap[+fStan]
  const podkategorie = wybraneStan?.podkategorie || []

  const load = useCallback(async () => {
    const [s, e] = week.split('|')
    setLoading(true)
    try {
      await reloadDicts()
      setWymagania(await api(`/wymagania?start=${s}&end=${e}`))
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [week, reloadDicts, toast])

  useEffect(() => {
    load()
  }, [load])

  const onSubcat = (val) => {
    setFSubcat(val)
    const pk = podkategorie.find((x) => x.id === +val)
    if (pk) {
      setFRewir(pk.nazwa || '')
      setFOd(pk.godz_od ? hhmm(pk.godz_od) : '')
    }
  }

  const dodaj = async () => {
    if (!fStan) {
      toast('Wybierz stanowisko.', 'error')
      return
    }
    try {
      await api('/wymagania', 'POST', {
        data: fData,
        stanowisko_id: +fStan,
        liczba_osob: +fLiczba,
        godz_od: fOd ? `${fOd}:00` : null,
        rewir: fRewir || null,
      })
      setFRewir('')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const kopiuj = async () => {
    if (!kopSource || !kopStart || !kopEnd) {
      toast('Uzupełnij daty kopiowania.', 'error')
      return
    }
    try {
      const r = await api('/wymagania/kopiuj', 'POST', { source_date: kopSource, start_date: kopStart, end_date: kopEnd })
      toast(`Skopiowano ${r.skopiowano ?? ''} wpisów.`, 'success')
      load()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

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
        <WeekSelect />
        <span className="text-sm text-muted">Zaplanowane wymagania na wybrany tydzień</span>
      </div>

      {/* Lista dni */}
      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : dni.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted">Brak wymagań na ten tydzień. Dodaj je w formularzu poniżej.</Card>
      ) : (
        <div className="space-y-3">
          {dni.map(({ data, items }) => {
            const dObj = new Date(data)
            return (
              <details key={data} open className="card overflow-hidden">
                <summary className="flex cursor-pointer list-none items-center justify-between p-4 font-bold text-ink transition hover:bg-white/[0.03] [&::-webkit-details-marker]:hidden">
                  <span>
                    {NAZWY_DNI[dObj.getDay()]} <span className="text-muted">({ddmmyyyy(data)})</span>
                  </span>
                  <Icon name="chevronDown" className="h-4 w-4 text-muted" />
                </summary>
                <div className="space-y-3 border-t border-line p-4">
                  {items.map((w) => (
                    <WymRow key={w.id} w={w} nazwa={stanMap[w.stanowisko_id]?.nazwa || '—'} onChanged={load} />
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
        <Card className="p-6">
          <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-bold text-ink">
            <Icon name="plus" className="h-5 w-5 text-mint" /> Zaplanuj zmianę
          </h3>
          <div className="mx-auto max-w-md space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Data</span>
                <input type="date" value={fData} onChange={(e) => setFData(e.target.value)} className="field" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Stanowisko</span>
                <select
                  value={fStan}
                  onChange={(e) => {
                    setFStan(e.target.value)
                    setFSubcat('')
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
                <select value={fSubcat} onChange={(e) => onSubcat(e.target.value)} className="field">
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
                <input type="time" value={fOd} onChange={(e) => setFOd(e.target.value)} className="field" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Liczba osób</span>
                <input type="number" min="1" value={fLiczba} onChange={(e) => setFLiczba(e.target.value)} className="field text-center font-bold" />
              </label>
            </div>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Rewir / strefa</span>
              <input value={fRewir} onChange={(e) => setFRewir(e.target.value)} placeholder="np. BarR1…" className="field" />
            </label>
            <Button variant="success" className="w-full" onClick={dodaj}>
              Dodaj do planu
            </Button>
          </div>
        </Card>

        {/* Kopiowanie */}
        <Card className="h-fit p-6">
          <h3 className="mb-2 flex items-center gap-2 font-display text-lg font-bold text-ink">
            <Icon name="clipboard" className="h-5 w-5 text-info" /> Kopiowanie (Pn–Pt)
          </h3>
          <p className="mb-4 text-xs text-muted">Wybierz wzorcowy dzień i skopiuj go na resztę tygodnia.</p>
          <div className="mx-auto max-w-md space-y-4">
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Źródło (kopiuj z)</span>
              <input type="date" value={kopSource} onChange={(e) => setKopSource(e.target.value)} className="field" />
            </label>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Od dnia</span>
                <input type="date" value={kopStart} onChange={(e) => setKopStart(e.target.value)} className="field" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Do dnia</span>
                <input type="date" value={kopEnd} onChange={(e) => setKopEnd(e.target.value)} className="field" />
              </label>
            </div>
            <Button className="w-full" onClick={kopiuj}>
              Duplikuj harmonogram
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}
