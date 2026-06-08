import { useEffect, useState, useCallback } from 'react'
import { Card } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, NAZWY_DNI } from '../../lib/format'

// Dzisiejsza data lokalnie (= Europe/Warsaw w przeglądarce) jako 'YYYY-MM-DD'.
const dzisISO = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
// Bieżąca godzina 'HH:MM' do porównań leksykalnych z bucketami godzinowymi (zero-padded).
const terazHHMM = () => {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// Rezerwacje (admin + szef): nagłówek = ile jeszcze DZIŚ przyjdzie, dni zwijane
// (mniej scrollowania; dzisiejszy dzień otwarty domyślnie). Dane z Google Calendar, co 60 s.
export default function Rezerwacje() {
  const { toast } = useToast()
  const [dni, setDni] = useState([])
  const [loading, setLoading] = useState(true)
  const [otwarte, setOtwarte] = useState({})

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setDni((await api('/rezerwacje')).dni || [])
    } catch (e) {
      if (!silent) toast(e.message, 'error')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, 60000)
    return () => clearInterval(id)
  }, [load])

  const toggle = (data, otwartyTeraz) => setOtwarte((o) => ({ ...o, [data]: !otwartyTeraz }))

  const today = dzisISO()

  // Nagłówek: ile rezerwacji/osób ma JESZCZE dziś przyjść (godzina startu >= teraz).
  const teraz = terazHHMM()
  const dzis = dni.find((d) => d.data === today)
  let dzisRez = 0
  let dzisOsob = 0
  if (dzis) {
    dzis.godziny.forEach((g) => {
      if (g.godzina >= teraz) {
        dzisRez += g.liczba
        dzisOsob += g.osoby
      }
    })
  }

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Rezerwacje</h2>
          <p className="mt-1 text-sm text-muted">Ile jeszcze dziś przyjdzie · dni rozwijane (na żywo).</p>
        </div>
        <div className="flex gap-6">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Jeszcze dziś</div>
            <div className="font-display text-2xl font-bold text-gradient tabular-nums">{dzisRez}</div>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Osoby</div>
            <div className="font-display text-2xl font-bold text-ink tabular-nums">{dzisOsob}</div>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : dni.length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted">
          Brak rezerwacji na najbliższe 30 dni (albo kalendarz nie jest jeszcze połączony).
        </Card>
      ) : (
        <div className="space-y-3">
          {dni.map((d) => {
            const isW = [0, 6].includes(new Date(d.data).getDay())
            // Domyślnie (zanim ktoś kliknie) otwarty jest tylko dzisiejszy dzień.
            const open = d.data in otwarte ? otwarte[d.data] : d.data === today
            return (
              <div key={d.data} className="overflow-hidden rounded-xl border border-line bg-white/[0.02]">
                <button
                  type="button"
                  onClick={() => toggle(d.data, open)}
                  className="flex w-full items-center gap-2 p-4 text-left transition active:scale-[0.99]"
                  style={{ WebkitTapHighlightColor: 'transparent' }}
                >
                  <div className="flex items-baseline gap-2">
                    <span className={`font-semibold capitalize ${isW ? 'text-blush' : 'text-ink'}`}>{NAZWY_DNI[new Date(d.data).getDay()]}</span>
                    <span className="text-xs text-muted">{ddmmyyyy(d.data)}</span>
                    {d.data === today && <span className="rounded-md bg-accent-gradient px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-bg">dziś</span>}
                  </div>
                  <span className="ml-auto text-sm font-bold text-ink">{d.liczba} rez. · {d.osoby} os.</span>
                  <Icon name="chevronDown" className={`h-4 w-4 shrink-0 text-muted transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
                </button>

                {/* Zwijanie pionowe (grid-rows 0fr↔1fr) — czysty CSS, bez mierzenia wysokości. */}
                <div className="grid transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]" style={{ gridTemplateRows: open ? '1fr' : '0fr' }}>
                  <div className="min-h-0 overflow-hidden">
                    <div className="space-y-1 px-4 pb-4">
                      {d.godziny.map((g) => (
                        <div key={g.godzina} className="flex items-center gap-3 border-b border-line/50 py-1 text-sm last:border-0">
                          <span className="w-16 shrink-0 font-mono font-semibold text-ink">{g.godzina}</span>
                          <span className="text-muted">{g.liczba} rez.</span>
                          <span className="ml-auto font-mono font-bold tabular-nums text-ink">{g.osoby} os.</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
