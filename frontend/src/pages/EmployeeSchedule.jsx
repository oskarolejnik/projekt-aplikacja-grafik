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
import RozliczImpreze from '../components/RozliczImpreze'
import RozliczSale from '../components/RozliczSale'

const dataLokalna = (d = new Date()) => [
  d.getFullYear(),
  String(d.getMonth() + 1).padStart(2, '0'),
  String(d.getDate()).padStart(2, '0'),
].join('-')

// „Mój grafik" — pracownik widzi swoje zmiany TYLKO po udostępnieniu przez admina:
// dzień, godzina, stanowisko + rewir oraz z kim dzieli rewir.
export default function EmployeeSchedule({ onSeen }) {
  const { week, biezacy, przyszly, setWeek } = useData()
  const { toast } = useToast()
  const [stan, setStan] = useState({ opublikowany: false, zmiany: [] })
  const [loading, setLoading] = useState(true)
  const [rozliczImp, setRozliczImp] = useState(null)   // { data, rewir } — modal rozliczenia imprezy
  const [rozliczSala, setRozliczSala] = useState(null) // { data } — modal „Rozlicz się" (sala)
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

  const teraz = new Date()
  const dzis = dataLokalna(teraz)
  const terazGodzina = `${String(teraz.getHours()).padStart(2, '0')}:${String(teraz.getMinutes()).padStart(2, '0')}`
  const najblizszaZmiana = useMemo(
    () => [...(stan.zmiany || [])]
      .filter((z) => z.data > dzis || (z.data === dzis && (!z.godz_od || z.godz_od >= terazGodzina)))
      .sort((a, b) => `${a.data} ${a.godz_od || '00:00'}`.localeCompare(`${b.data} ${b.godz_od || '00:00'}`))[0] || null,
    [stan.zmiany, dzis, terazGodzina],
  )

  return (
    <>
      {!loading && stan.opublikowany && najblizszaZmiana && (
        <section
          aria-labelledby="najblizsza-zmiana-title"
          className="mb-6 rounded-2xl border border-mint/30 bg-mint/[0.06] p-5 sm:p-6"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 id="najblizsza-zmiana-title" className="text-sm font-semibold text-mint">
                {najblizszaZmiana.data === dzis ? 'Dzisiejsza zmiana' : 'Najbliższa zmiana'}
              </h2>
              <p className="mt-1 font-display text-2xl font-bold capitalize text-ink">
                {NAZWY_DNI[new Date(`${najblizszaZmiana.data}T12:00:00`).getDay()]}
                <span className="ml-2 text-base font-semibold text-muted">{ddmmyyyy(najblizszaZmiana.data)}</span>
              </p>
            </div>
            <div className={najblizszaZmiana.godz_od
              ? 'font-mono text-3xl font-bold tabular-nums text-ink'
              : 'rounded-lg bg-white/[0.05] px-3 py-2 text-sm font-semibold text-muted'}>
              {najblizszaZmiana.godz_od || 'Godzina do ustalenia'}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-lg bg-white/[0.06] px-3 py-1.5 font-semibold text-ink">
              {najblizszaZmiana.stanowisko}
            </span>
            {najblizszaZmiana.rewir && (
              <span className="rounded-lg bg-mint/10 px-3 py-1.5 font-semibold text-mint">{najblizszaZmiana.rewir}</span>
            )}
            {najblizszaZmiana.zamyka && (
              <span className="inline-flex items-center gap-1 rounded-lg bg-lemon/15 px-3 py-1.5 font-semibold text-lemon">
                <Icon name="key" className="h-4 w-4" /> Zamykasz
              </span>
            )}
            {najblizszaZmiana.zamyka_rewir && (
              <span className="inline-flex items-center gap-1 rounded-lg bg-mint/15 px-3 py-1.5 font-semibold text-mint">
                <Icon name="key" className="h-4 w-4" /> Zamykasz rewir
              </span>
            )}
          </div>
        </section>
      )}

      {!loading && stan.opublikowany && week === biezacy && !najblizszaZmiana && (
        <div className="mb-6 flex flex-col gap-3 rounded-xl border border-line bg-white/[0.03] px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <span className="text-muted">
            {dni.length === 0 ? 'Nie masz przydzielonych zmian w tym tygodniu.' : 'Nie masz już kolejnych zmian w tym tygodniu.'}
          </span>
          <button
            type="button"
            onClick={() => setWeek(przyszly)}
            className="min-h-11 shrink-0 rounded-xl border border-line bg-white/[0.04] px-4 py-2 font-semibold text-ink transition hover:border-mint/40 hover:text-mint active:scale-[0.98]"
          >
            Pokaż następny tydzień
          </button>
        </div>
      )}

      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <WeekSelect />
        <span className="text-sm text-muted">Twój grafik na wybrany tydzień.</span>
      </div>

      {/* „Rozlicz się" — globalne, na podstawie realnych zamkniętych rozliczeń w Gastro
          (niezależne od oglądanego tygodnia i daty zmiany w grafiku). */}
      {(stan.rozliczenia_oczekujace?.length > 0) && (
        <Card className="mb-4 border-coral/40 bg-coral/[0.06] p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-bold text-coral">
            <Icon name="clipboard" className="h-4 w-4" />
            {stan.rozliczenia_oczekujace.length === 1
              ? 'Masz rozliczenie do przesłania'
              : `Masz ${stan.rozliczenia_oczekujace.length} rozliczenia do przesłania`}
          </div>
          <div className="flex flex-wrap gap-2">
            {stan.rozliczenia_oczekujace.map((d) => (
              <button key={d} type="button" onClick={() => setRozliczSala({ data: d })}
                className="flex min-h-11 items-center gap-2 rounded-lg bg-coral/15 px-3 py-2 text-sm font-semibold text-coral transition hover:bg-coral/25">
                <Icon name="clipboard" className="h-4 w-4" /> Rozlicz się — {ddmmyyyy(d)}
              </button>
            ))}
          </div>
        </Card>
      )}

      {(loading || !stan.opublikowany || dni.length > 0 || week !== biezacy) && (
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
            {dni.map(({ data, zmiany }, i) => {
              return (
              <div key={data} className="animate-fade-up rounded-xl border border-line bg-white/[0.02] p-4" style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
                <div className="mb-3 flex items-baseline gap-2">
                  <span className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(`${data}T12:00:00`).getDay()]}</span>
                  <span className="text-xs text-muted">{ddmmyyyy(data)}</span>
                </div>
                <div className="space-y-2">
                  {zmiany.map((z, i) => (
                    <div key={i} className={`rounded-lg border bg-surface-2 p-3 ${z.zamyka ? 'border-lemon/40' : 'border-line'}`}>
                      <div className="flex flex-wrap items-center gap-2">
                        {z.godz_od && (
                          <span className="rounded-md bg-white/[0.06] px-2 py-0.5 font-mono text-sm font-bold text-ink">{z.godz_od}</span>
                        )}
                        <span className="font-bold text-ink">{z.stanowisko}</span>
                        {z.rewir && <span className="text-sm font-semibold text-mint">{z.rewir}</span>}
                        {z.zamyka && (
                          <span className="inline-flex items-center gap-1 rounded-md bg-lemon/15 px-2 py-0.5 text-xs font-semibold text-lemon">
                            <Icon name="key" className="h-3 w-3" /> Zamykasz
                          </span>
                        )}
                        {z.zamyka_rewir && (
                          <span className="inline-flex items-center gap-1 rounded-md bg-mint/15 px-2 py-0.5 text-xs font-semibold text-mint">
                            <Icon name="key" className="h-3 w-3" /> Zamykasz rewir
                          </span>
                        )}
                        {z.rozlicza_imprize && (
                          <button
                            type="button"
                            onClick={() => setRozliczImp({ data: z.data, rewir: z.rewir })}
                            className="inline-flex items-center gap-1 rounded-md bg-coral/15 px-2 py-0.5 text-xs font-semibold text-coral transition hover:bg-coral/25"
                          >
                            <Icon name="clipboard" className="h-3 w-3" /> Rozlicz imprezę
                          </button>
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
              )
            })}
          </div>
        )}
        </Card>
      )}

      {rozliczImp && (
        <RozliczImpreze
          data={rozliczImp.data}
          rewir={rozliczImp.rewir}
          onClose={(zmiana) => { setRozliczImp(null); if (zmiana) load() }}
        />
      )}

      {rozliczSala && (
        <RozliczSale
          data={rozliczSala.data}
          onClose={(zmiana) => { setRozliczSala(null); if (zmiana) load() }}
        />
      )}
    </>
  )
}
