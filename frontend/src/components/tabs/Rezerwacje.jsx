import { useCallback, useEffect, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { ddmmyyyy, NAZWY_DNI } from '../../lib/format'
import { warsawDateISO } from '../../lib/date'

const terazWarszawaHHMM = (date = new Date()) => new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'Europe/Warsaw',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
}).format(date)

const indeksDnia = (iso) => {
  const [rok, miesiac, dzien] = String(iso || '').split('-').map(Number)
  if (!rok || !miesiac || !dzien) return 0
  return new Date(Date.UTC(rok, miesiac - 1, dzien)).getUTCDay()
}

const poprawneDni = (payload) => (
  Array.isArray(payload?.dni)
  && payload.dni.every((dzien) => (
    typeof dzien?.data === 'string'
    && Array.isArray(dzien.godziny)
  ))
)

// Kompaktowy, bezpieczny agregat dla pracownika i kuchni. Pierwsze ładowanie ma
// osobny stan, a późniejsze odświeżenia nigdy nie usuwają ostatniego snapshotu.
export default function Rezerwacje() {
  const [dni, setDni] = useState([])
  const [maSnapshot, setMaSnapshot] = useState(false)
  const [pierwszeLadowanie, setPierwszeLadowanie] = useState(true)
  const [odswiezanie, setOdswiezanie] = useState(false)
  const [blad, setBlad] = useState('')
  const [ostatniaAktualizacja, setOstatniaAktualizacja] = useState(null)
  const [otwarte, setOtwarte] = useState({})
  const maSnapshotRef = useRef(false)
  const requestRef = useRef(null)

  const load = useCallback(async () => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    const initial = !maSnapshotRef.current

    setBlad('')
    if (initial) setPierwszeLadowanie(true)
    else setOdswiezanie(true)

    try {
      const payload = await api('/rezerwacje', 'GET', null, { signal: controller.signal })
      if (!poprawneDni(payload)) {
        throw new Error('Serwer zwrócił niepełne dane rezerwacji.')
      }
      if (requestRef.current !== controller) return

      setDni(payload.dni)
      maSnapshotRef.current = true
      setMaSnapshot(true)
      setOstatniaAktualizacja(new Date())
    } catch (e) {
      if (e?.name === 'AbortError' || requestRef.current !== controller) return
      setBlad(e?.message || 'Nie udało się pobrać rezerwacji.')
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null
        setPierwszeLadowanie(false)
        setOdswiezanie(false)
      }
    }
  }, [])

  useEffect(() => {
    void load()
    return () => {
      requestRef.current?.abort()
      requestRef.current = null
    }
  }, [load])

  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') void load()
    }, 60000)
    return () => clearInterval(id)
  }, [load])

  const toggle = (data, otwartyTeraz) => setOtwarte((o) => ({ ...o, [data]: !otwartyTeraz }))

  const today = warsawDateISO()

  // Nagłówek: ile rezerwacji/osób ma JESZCZE dziś przyjść (godzina startu >= teraz).
  const teraz = terazWarszawaHHMM()
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
      <SectionHeader title="Rezerwacje" subtitle="Lista najbliższych rezerwacji. Aktualizuje się automatycznie.">
        <div className="flex items-center gap-3">
          {maSnapshot && (
            <Button
              variant="subtle"
              size="sm"
              onClick={() => void load()}
              loading={odswiezanie}
              loadingLabel="Odświeżam rezerwacje"
              aria-label="Odśwież rezerwacje"
            >
              <Icon name="refresh" className="h-4 w-4" />
              Odśwież
            </Button>
          )}
          <div className="text-right">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Jeszcze dziś</div>
            <div className="flex items-baseline justify-end gap-2">
              <span className="font-display text-3xl font-bold text-ink tabular-nums">
                {maSnapshot ? dzisRez : '—'}
              </span>
              <span className="text-sm font-semibold text-muted">rez.</span>
              <span className="text-sm text-muted">· {maSnapshot ? dzisOsob : '—'} os.</span>
            </div>
          </div>
        </div>
      </SectionHeader>

      {maSnapshot && (
        <div className="mb-4 min-h-5 text-xs text-muted" role="status" aria-live="polite">
          {odswiezanie ? (
            <span className="inline-flex items-center gap-2">
              <Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" />
              Aktualizuję listę…
            </span>
          ) : ostatniaAktualizacja ? (
            <>Ostatnia aktualizacja: {terazWarszawaHHMM(ostatniaAktualizacja)}</>
          ) : null}
        </div>
      )}

      {blad && (
        <div
          className="mb-4 flex flex-col gap-3 rounded-xl border border-danger/30 bg-danger/10 p-4 sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <div>
            <p className="font-semibold text-ink">
              {maSnapshot ? 'Nie udało się odświeżyć listy' : 'Nie udało się pobrać rezerwacji'}
            </p>
            <p className="mt-1 text-sm text-muted">
              {maSnapshot ? 'Pokazuję ostatnie poprawnie pobrane dane. ' : ''}
              {blad}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            <Icon name="refresh" className="h-4 w-4" />
            Ponów
          </Button>
        </div>
      )}

      {pierwszeLadowanie && !maSnapshot ? (
        <div
          className="grid min-h-48 place-items-center py-12 text-center"
          role="status"
          aria-label="Ładowanie rezerwacji"
        >
          <div>
            <Spinner className="mx-auto h-6 w-6 text-muted motion-reduce:animate-none" />
            <p className="mt-3 text-sm text-muted">Ładuję rezerwacje…</p>
          </div>
        </div>
      ) : !maSnapshot ? null : dni.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] px-5 py-10 text-center">
          <p className="font-semibold text-ink">Brak rezerwacji na najbliższe 30 dni</p>
          <p className="mt-1 text-sm text-muted">Nowe rezerwacje pojawią się tutaj automatycznie.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {dni.map((d) => {
            const dayIndex = indeksDnia(d.data)
            // Domyślnie (zanim ktoś kliknie) otwarty jest tylko dzisiejszy dzień.
            const open = d.data in otwarte ? otwarte[d.data] : d.data === today
            const detailsId = `rezerwacje-dzien-${d.data}`
            return (
              <div key={d.data} className="overflow-hidden rounded-xl border border-line bg-white/[0.02]">
                <button
                  type="button"
                  onClick={() => toggle(d.data, open)}
                  aria-expanded={open}
                  aria-controls={detailsId}
                  className="flex min-h-14 w-full items-center gap-3 px-4 py-3 text-left transition duration-150 ease-snap hover:bg-white/[0.03] active:scale-[0.99]"
                  style={{ WebkitTapHighlightColor: 'transparent' }}
                >
                  <div className="flex min-w-0 flex-1 items-baseline gap-2">
                    <span className="truncate font-semibold capitalize text-ink">{NAZWY_DNI[dayIndex]}</span>
                    <span className="shrink-0 text-xs text-muted">{ddmmyyyy(d.data).slice(0, 5)}</span>
                    {d.data === today && (
                      <span className="shrink-0 rounded-md bg-mint px-1.5 py-0.5 text-[11px] font-semibold text-bg">
                        dziś
                      </span>
                    )}
                  </div>
                  <span className="flex shrink-0 items-baseline gap-1.5">
                    <span className="text-lg font-bold tabular-nums text-ink">{d.liczba}</span>
                    <span className="text-xs text-muted">rez. · {d.osoby} os.</span>
                  </span>
                  <Icon name="chevronDown" className={`h-4 w-4 shrink-0 text-muted transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
                </button>

                {/* Zwijanie pionowe (grid-rows 0fr↔1fr) — czysty CSS, bez mierzenia wysokości. */}
                <div
                  id={detailsId}
                  aria-hidden={!open}
                  inert={!open ? '' : undefined}
                  className="grid transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]"
                  style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
                >
                  <div className="min-h-0 overflow-hidden">
                    <div className="space-y-1 px-4 pb-4">
                      {d.godziny.map((g) => (
                        <div key={g.godzina} className="flex min-h-11 items-center gap-3 border-b border-line/50 py-2 text-sm last:border-0">
                          <span className="w-14 shrink-0 font-mono font-semibold text-muted">{g.godzina}</span>
                          <span className="text-base font-bold tabular-nums text-ink">{g.liczba}</span>
                          <span className="text-xs text-muted">rez.</span>
                          <span className="ml-auto text-xs text-muted">{g.osoby} os.</span>
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
