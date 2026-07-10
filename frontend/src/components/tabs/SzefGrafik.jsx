import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { WeekSelect } from '../ui/WeekSelect'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { hhmm, ddmmyyyy, NAZWY_DNI, zakresDni } from '../../lib/format'

const dzisISO = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const lokalnaData = (iso) => new Date(`${iso}T12:00:00`)

const pelnaData = (iso) => {
  const tekst = new Intl.DateTimeFormat('pl-PL', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(lokalnaData(iso))
  return tekst.charAt(0).toUpperCase() + tekst.slice(1)
}

const odmiana = (n, jeden, kilka, wiele) => {
  if (n === 1) return jeden
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return kilka
  return wiele
}

function ZnacznikiZmiany({ zmiana }) {
  const znaczniki = [
    zmiana.zamyka && 'Zamyka lokal',
    zmiana.zamyka_rewir && 'Zamyka rewir',
    zmiana.rozlicza_imprize && 'Rozlicza imprezę',
  ].filter(Boolean)
  if (znaczniki.length === 0) return null
  return (
    <span className="flex flex-wrap gap-1.5">
      {znaczniki.map((tekst) => (
        <span key={tekst} className="rounded-md bg-white/[0.06] px-2 py-1 text-[11px] font-semibold text-muted">
          {tekst}
        </span>
      ))}
    </span>
  )
}

function WierszZmiany({ zmiana, pracMap, stanMap, pokazStanowisko = false }) {
  return (
    <li className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-3 py-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-center">
      <time className={`font-mono text-xs font-semibold ${zmiana.godz_od ? 'text-ink' : 'text-lemon'}`}>
        {zmiana.godz_od ? hhmm(zmiana.godz_od) : 'Do ustalenia'}
      </time>
      <div className="min-w-0">
        <div className="font-semibold text-ink">{pracMap[zmiana.pracownik_id] || 'Nieznany pracownik'}</div>
        {(pokazStanowisko || zmiana.rewir) && (
          <div className="mt-0.5 text-xs text-muted">
            {pokazStanowisko ? stanMap[zmiana.stanowisko_id] || 'Stanowisko' : null}
            {pokazStanowisko && zmiana.rewir ? ' · ' : null}
            {zmiana.rewir || null}
          </div>
        )}
      </div>
      <span className="col-start-2 sm:col-start-3">
        <ZnacznikiZmiany zmiana={zmiana} />
      </span>
    </li>
  )
}

function DzienOkresu({ data, zmiany, pracMap, stanMap }) {
  const dt = lokalnaData(data)
  const weekend = [0, 6].includes(dt.getDay())
  return (
    <section className="py-4" aria-labelledby={`grafik-${data}`}>
      <div className="mb-1 flex items-baseline gap-2">
        <h3 id={`grafik-${data}`} className={`font-semibold capitalize ${weekend ? 'text-blush' : 'text-ink'}`}>
          {NAZWY_DNI[dt.getDay()]}
        </h3>
        <time dateTime={data} className="text-xs text-muted">{ddmmyyyy(data)}</time>
        <span className="ml-auto text-xs text-muted">
          {zmiany.length} {odmiana(zmiany.length, 'zmiana', 'zmiany', 'zmian')}
        </span>
      </div>
      {zmiany.length === 0 ? (
        <p className="py-2 text-sm text-muted">Brak zaplanowanych zmian.</p>
      ) : (
        <ul className="divide-y divide-line/60">
          {zmiany.map((zmiana) => (
            <WierszZmiany
              key={zmiana.id}
              zmiana={zmiana}
              pracMap={pracMap}
              stanMap={stanMap}
              pokazStanowisko
            />
          ))}
        </ul>
      )}
    </section>
  )
}

// Published-only widok managera: najpierw dzisiejsza obsada i uwagi, potem reszta okresu.
export default function SzefGrafik({ onOpenLive }) {
  const { stanowiska, pracownicy, week, reloadDicts } = useData()
  const [dane, setDane] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const requestIdRef = useRef(0)

  const [s, e] = week.split('|')
  const dni = useMemo(() => zakresDni(s, e), [s, e])
  const stanMap = useMemo(() => Object.fromEntries(stanowiska.map((x) => [x.id, x.nazwa])), [stanowiska])
  const pracMap = useMemo(() => Object.fromEntries(pracownicy.map((p) => [p.id, `${p.imie} ${p.nazwisko}`])), [pracownicy])

  const load = useCallback(async (silent = false) => {
    const requestId = ++requestIdRef.current
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    try {
      const request = api(`/szef/grafik?start=${s}&end=${e}`)
      const dictionaries = Promise.resolve().then(() => reloadDicts())
      if (silent) void dictionaries.catch(() => {})
      const next = silent ? await request : (await Promise.all([dictionaries, request]))[1]
      if (requestId === requestIdRef.current) {
        setDane(next)
        setError(null)
      }
    } catch (err) {
      if (!silent && requestId === requestIdRef.current) {
        setDane(null)
        setError(err.message || 'Nie udało się pobrać grafiku.')
      }
    } finally {
      if (!silent && requestId === requestIdRef.current) setLoading(false)
    }
  }, [s, e, reloadDicts])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, 20000)
    return () => clearInterval(id)
  }, [load])

  useEffect(() => () => { requestIdRef.current += 1 }, [])

  const perDzien = useMemo(() => {
    const mapa = {}
    for (const zmiana of dane?.przydzialy || []) {
      ;(mapa[zmiana.data] = mapa[zmiana.data] || []).push(zmiana)
    }
    Object.values(mapa).forEach((lista) => lista.sort((a, b) =>
      String(a.godz_od || '99:99').localeCompare(String(b.godz_od || '99:99'))))
    return mapa
  }, [dane])

  const dzis = dzisISO()
  const okresObejmujeDzis = dni.includes(dzis)
  const zmianyDzis = okresObejmujeDzis ? (perDzien[dzis] || []) : []
  const pozostaleDni = okresObejmujeDzis ? dni.filter((d) => d !== dzis) : dni
  const osobyDzis = new Set(zmianyDzis.map((z) => z.pracownik_id)).size
  const stanowiskaDzis = new Set(zmianyDzis.map((z) => z.stanowisko_id)).size
  const bezGodziny = zmianyDzis.filter((z) => !z.godz_od)
  const grupyDzis = useMemo(() => {
    const grupy = new Map()
    for (const zmiana of zmianyDzis) {
      const nazwa = stanMap[zmiana.stanowisko_id] || 'Pozostałe'
      if (!grupy.has(nazwa)) grupy.set(nazwa, [])
      grupy.get(nazwa).push(zmiana)
    }
    return [...grupy.entries()].sort(([a], [b]) => a.localeCompare(b, 'pl'))
  }, [zmianyDzis, stanMap])
  const maUwagi = (dane?.alerty_dzis?.length || 0) > 0 || bezGodziny.length > 0

  return (
    <Card className="p-6 md:p-8">
      <SectionHeader
        title={okresObejmujeDzis ? 'Grafik na dziś' : 'Grafik'}
        subtitle="Wyłącznie opublikowany grafik. Dzisiejsza obsada jest zawsze pierwsza."
      >
        <WeekSelect />
      </SectionHeader>

      {loading ? (
        <div className="space-y-4 py-8" role="status" aria-label="Wczytywanie grafiku">
          <span className="sr-only">Wczytywanie grafiku…</span>
          <div className="h-6 w-40 animate-pulse rounded-lg bg-white/[0.06]" />
          <div className="h-20 animate-pulse rounded-xl bg-white/[0.04]" />
          <div className="h-12 animate-pulse rounded-xl bg-white/[0.03]" />
        </div>
      ) : error ? (
        <Banner variant="danger">
          <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
            <span>Nie udało się pobrać grafiku. {error}</span>
            <Button size="sm" variant="ghost" onClick={() => load()}>
              Spróbuj ponownie
            </Button>
          </div>
        </Banner>
      ) : !dane?.opublikowany ? (
        <Banner variant="warn">Grafik na ten okres nie został jeszcze opublikowany.</Banner>
      ) : (
        <>
          {okresObejmujeDzis && (
            <section className="border-y border-line py-5" aria-labelledby="grafik-dzisiaj">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted">Dzisiaj</p>
                  <h3 id="grafik-dzisiaj" className="mt-1 font-display text-xl font-semibold text-ink">
                    {pelnaData(dzis)}
                  </h3>
                  <p className="mt-1 text-sm text-muted">
                    {osobyDzis} {odmiana(osobyDzis, 'osoba', 'osoby', 'osób')} · {stanowiskaDzis}{' '}
                    {odmiana(stanowiskaDzis, 'stanowisko', 'stanowiska', 'stanowisk')}
                  </p>
                </div>
                {onOpenLive && (
                  <Button variant="ghost" onClick={onOpenLive}>
                    <Icon name="pin" className="h-4 w-4" /> Sala na żywo
                  </Button>
                )}
              </div>

              {maUwagi && (
                <Banner variant="warn" className="mt-5">
                  <div>
                    <div className="font-semibold">Wymaga uwagi</div>
                    <ul className="mt-1 space-y-1 text-xs">
                      {(dane.alerty_dzis || []).map((alert) => (
                        <li key={`${alert.data}:${alert.stanowisko}`}>
                          {alert.stanowisko}: brakuje {alert.brakuje} (obsadzone {alert.obsadzone}/{alert.wymagane}).
                        </li>
                      ))}
                      {bezGodziny.length > 0 && (
                        <li>
                          {bezGodziny.length} {odmiana(bezGodziny.length, 'zmiana nie ma', 'zmiany nie mają', 'zmian nie ma')} godziny rozpoczęcia.
                        </li>
                      )}
                    </ul>
                  </div>
                </Banner>
              )}

              {zmianyDzis.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted">
                  Dziś nikt nie jest wpisany do opublikowanego grafiku.
                </p>
              ) : (
                <div className="mt-5 divide-y divide-line">
                  {grupyDzis.map(([stanowisko, zmiany]) => (
                    <section key={stanowisko} className="py-4 first:pt-0 last:pb-0" aria-label={stanowisko}>
                      <div className="mb-1 flex items-center justify-between gap-3">
                        <h4 className="text-sm font-semibold text-ink">{stanowisko}</h4>
                        <span className="text-xs text-muted">
                          {zmiany.length} {odmiana(zmiany.length, 'zmiana', 'zmiany', 'zmian')}
                        </span>
                      </div>
                      <ul className="divide-y divide-line/60">
                        {zmiany.map((zmiana) => (
                          <WierszZmiany key={zmiana.id} zmiana={zmiana} pracMap={pracMap} stanMap={stanMap} />
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              )}
            </section>
          )}

          {okresObejmujeDzis ? (
            <details className="group border-b border-line">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 py-4 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
                <span>Pozostałe dni okresu</span>
                <Icon name="chevronDown" className="h-4 w-4 text-muted transition group-open:rotate-180" />
              </summary>
              <div className="divide-y divide-line">
                {pozostaleDni.map((data) => (
                  <DzienOkresu key={data} data={data} zmiany={perDzien[data] || []} pracMap={pracMap} stanMap={stanMap} />
                ))}
              </div>
            </details>
          ) : (
            <div className="divide-y divide-line">
              {pozostaleDni.map((data) => (
                <DzienOkresu key={data} data={data} zmiany={perDzien[data] || []} pracMap={pracMap} stanMap={stanMap} />
              ))}
            </div>
          )}
        </>
      )}
    </Card>
  )
}
