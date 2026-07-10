import { useEffect, useState, useCallback, useRef } from 'react'
import { Card } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { warsawDateISO } from '../../lib/date'

// Pulpit właściciela — KPI lokalu w okresie. Czysta agregacja z /api/pulpit (zero zapisu).
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const przesunISO = (iso, days) => {
  const [year, month, day] = iso.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
const dzisISO = () => warsawDateISO()
const isoMinus = (days) => przesunISO(dzisISO(), -days)
const dataKrotko = (iso) => new Intl.DateTimeFormat('pl-PL', {
  day: '2-digit',
  month: '2-digit',
}).format(new Date(`${iso}T12:00:00`))

const STATUS_L = { rezerwacja: 'Rezerwacje', potwierdzona: 'Potwierdzone', odbyla: 'Odbyłe', no_show: 'No-show', odwolana: 'Odwołane' }

function Kpi({ label, value, sub, icon, accent }) {
  return (
    <div className="rounded-2xl border border-line bg-surface-2 p-5">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
        {icon && <Icon name={icon} className="h-4 w-4" />} {label}
      </div>
      <div className={`font-display text-2xl font-bold ${accent || 'text-ink'}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  )
}

function PulpitSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Wczytywanie pulpitu">
      <span className="sr-only">Wczytywanie pulpitu…</span>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className="h-[7.25rem] animate-pulse rounded-2xl border border-line bg-white/[0.03]" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-[4.5rem] animate-pulse rounded-xl border border-line bg-white/[0.025]" />
        ))}
      </div>
    </div>
  )
}

export default function Pulpit() {
  const [start, setStart] = useState(isoMinus(29))
  const [end, setEnd] = useState(dzisISO())
  const [p, setP] = useState(null)
  const [alerty, setAlerty] = useState(null)
  const [obsada, setObsada] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [partialError, setPartialError] = useState([])
  const [updatedAt, setUpdatedAt] = useState(null)
  const loadedRef = useRef(false)
  const requestIdRef = useRef(0)
  // Kafelek „Impreza" tylko w lokalach z osobnym rozliczaniem imprez.
  const [cfg, setCfg] = useState(null)
  useEffect(() => { api('/lokal/config').then(setCfg).catch(() => {}) }, [])

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current
    const initial = !loadedRef.current
    if (initial) setLoading(true)
    else setRefreshing(true)
    setError(null)
    try {
      const [pul, al, ob] = await Promise.allSettled([
        api(`/pulpit?start=${start}&end=${end}`),
        api(`/alerty-kasowe?start=${start}&end=${end}`),
        api('/alerty-obsady?dni=14'),
      ])
      if (requestId !== requestIdRef.current) return

      const braki = []
      if (pul.status === 'fulfilled') {
        setP(pul.value)
        loadedRef.current = true
        setUpdatedAt(new Date())

        if (al.status === 'fulfilled') setAlerty(al.value)
        else {
          setAlerty(null)
          braki.push('alertów kasowych')
        }
        if (ob.status === 'fulfilled') setObsada(ob.value)
        else {
          setObsada(null)
          braki.push('alertów obsady')
        }
        setPartialError(braki)
      } else {
        setError(pul.reason?.message || 'Nie udało się pobrać danych pulpitu.')
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [start, end])
  useEffect(() => { load() }, [load])
  useEffect(() => () => { requestIdRef.current += 1 }, [])

  const maxPrzychod = p ? Math.max(1, ...p.przychod.dzienny.map((d) => d.przychod)) : 1
  const alertyObsady = obsada?.alerty || []
  const alertyKasy = alerty?.alerty || []
  const liczbaAlertowKasy = p
    ? Math.max(alertyKasy.length, Number(p.alerty_kasowe?.dni_z_anomalia) || 0)
    : 0
  const liczbaDecyzji = alertyObsady.length + liczbaAlertowKasy
  const decyzjeNiepelne = partialError.length > 0

  return (
    <section aria-label="Pulpit właściciela" className="space-y-5">
      <div className="flex flex-col gap-4 rounded-2xl border border-line bg-white/[0.025] p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-xl text-sm leading-relaxed text-muted">
          Najpierw sprawy wymagające reakcji, potem wynik okresu.
        </p>
        <fieldset className="grid w-full grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 text-sm sm:w-auto">
          <legend className="sr-only">Zakres danych pulpitu</legend>
          <input aria-label="Początek okresu" type="date" value={start} onChange={(e) => setStart(e.target.value)} className="min-h-11 min-w-0 rounded-xl border border-line bg-surface px-3 py-1.5 text-ink outline-none focus:border-mint" />
          <span aria-hidden="true" className="text-muted">do</span>
          <input aria-label="Koniec okresu" type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="min-h-11 min-w-0 rounded-xl border border-line bg-surface px-3 py-1.5 text-ink outline-none focus:border-mint" />
        </fieldset>
      </div>

      {loading && !p ? (
        <PulpitSkeleton />
      ) : !p ? (
        <div role="alert">
          <Banner variant="danger">
            <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
              <span>Nie udało się wczytać pulpitu. {error}</span>
              <Button size="sm" variant="ghost" onClick={load}>Spróbuj ponownie</Button>
            </div>
          </Banner>
        </div>
      ) : (
        <div className="space-y-6" aria-busy={refreshing}>
          <div className="flex min-h-6 flex-wrap items-center justify-between gap-2 text-xs text-muted" aria-live="polite">
            <span>
              {refreshing ? (
                <span className="inline-flex items-center gap-2"><Spinner className="h-3.5 w-3.5" /> Aktualizuję dane…</span>
              ) : updatedAt ? `Zaktualizowano ${updatedAt.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' })}` : null}
            </span>
            {refreshing && <span>Poprzednie wyniki pozostają widoczne.</span>}
          </div>

          {error && (
            <div role="alert">
              <Banner variant="warn">
                <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
                  <span>Nie udało się odświeżyć KPI. Pokazujemy ostatnie dostępne dane. {error}</span>
                  <Button size="sm" variant="ghost" onClick={load}>Ponów</Button>
                </div>
              </Banner>
            </div>
          )}

          {partialError.length > 0 && (
            <div role="status" aria-live="polite">
              <Banner variant="info">
                Główne KPI są aktualne, ale nie udało się pobrać {partialError.join(' ani ')}. Niedostępne sekcje zostały ukryte i odświeżą się przy kolejnej próbie.
              </Banner>
            </div>
          )}

          <section aria-labelledby="pulpit-decyzje-title" className={`rounded-2xl border p-5 sm:p-6 ${
            liczbaDecyzji > 0
              ? 'border-lemon/25 bg-lemon/[0.035]'
              : decyzjeNiepelne
                ? 'border-line bg-white/[0.025]'
                : 'border-success/20 bg-success/[0.035]'
          }`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 id="pulpit-decyzje-title" className="font-display text-lg font-semibold text-ink">Wymaga decyzji</h3>
                <p className="mt-1 text-sm text-muted">
                  {liczbaDecyzji > 0
                    ? `${liczbaDecyzji} ${liczbaDecyzji === 1 ? 'sprawa' : liczbaDecyzji < 5 ? 'sprawy' : 'spraw'} do sprawdzenia.${decyzjeNiepelne ? ' Lista może być niepełna.' : ''}`
                    : decyzjeNiepelne
                      ? 'Nie udało się potwierdzić pełnego stanu alertów.'
                      : 'Na teraz wszystko jest pod kontrolą.'}
                </p>
              </div>
              <span className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                liczbaDecyzji > 0
                  ? 'bg-lemon/15 text-lemon'
                  : decyzjeNiepelne
                    ? 'bg-white/[0.06] text-muted'
                    : 'bg-success/15 text-success'
              }`}>
                {liczbaDecyzji > 0 ? 'Do działania' : decyzjeNiepelne ? 'Niepełne dane' : 'Bez pilnych spraw'}
              </span>
            </div>

            {liczbaDecyzji > 0 && (
              <div className="mt-5 space-y-2">
                {alertyObsady.length > 0 && (
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Obsada · najbliższe {obsada?.dni || 14} dni
                  </p>
                )}
                {alertyObsady.map((a, i) => (
                  <div key={`obsada-${a.data}-${a.stanowisko}-${i}`} className="flex flex-col gap-1 rounded-xl bg-black/10 px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                    <span className="text-ink"><time dateTime={a.data} className="font-semibold">{a.data}</time> · {a.stanowisko}</span>
                    <span className="text-muted">Obsadzone {a.obsadzone}/{a.wymagane}. <b className="text-lemon">Brakuje {a.brakuje}</b></span>
                  </div>
                ))}
                {liczbaAlertowKasy > 0 && (
                  <p className={`${alertyObsady.length > 0 ? 'pt-3' : ''} text-xs font-semibold uppercase tracking-wide text-muted`}>
                    Kasa · wybrany okres
                  </p>
                )}
                {alertyKasy.map((a) => (
                  <div key={`kasa-${a.data}`} className="rounded-xl bg-black/10 px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-ink">Kasa · <time dateTime={a.data}>{a.data}</time></span>
                      <span className="text-xs text-muted">{a.status}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      {a.problemy.map((problem, i) => (
                        <span key={i} className={`rounded-lg px-2 py-1 ${problem.roznica < 0 ? 'bg-danger/15 text-danger' : 'bg-lemon/15 text-lemon'}`}>
                          {problem.typ === 'karty' ? 'Karty' : 'Kasa'}: {zl(problem.roznica)}{problem.etykieta ? ` · ${problem.etykieta}` : ''}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
                {alertyKasy.length === 0 && liczbaAlertowKasy > 0 && (
                  <div className="rounded-xl bg-black/10 px-4 py-3 text-sm text-muted">
                    <b className="text-ink">Kasa:</b> {liczbaAlertowKasy} {liczbaAlertowKasy === 1 ? 'dzień wymaga' : 'dni wymagają'} sprawdzenia
                    {p.alerty_kasowe.suma_braki < 0 ? `, braki ${zl(p.alerty_kasowe.suma_braki)}` : '.'}
                  </div>
                )}
              </div>
            )}
          </section>

          <section aria-labelledby="pulpit-wynik-title">
            <h3 id="pulpit-wynik-title" className="mb-3 font-display text-lg font-semibold text-ink">Wynik okresu</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Kpi label="Przychód" value={zl(p.przychod.razem)} sub={`śr. ${zl(p.przychod.srednia_dzienna)}/dzień`} icon="download" accent="text-mint" />
              <Kpi label="Rozchód" value={zl(p.rozchod.razem)} icon="upload" />
              <Kpi label="Saldo kasy" value={zl(p.saldo_kasy)} sub="stan gotówki narastająco" icon="clipboard" />
              <Kpi label="Ruch (rachunki)" value={p.ruch.rachunki} sub={`śr. ${p.ruch.srednia_dzienna}/dzień`} icon="pin" />
              <Kpi label="Rezerwacje" value={p.rezerwacje.razem} sub={`${p.rezerwacje.goscie} gości`} icon="calendar" />
              <Kpi label={`Koszt pracy (${String(p.koszt_pracy_miesiac.miesiac).padStart(2, '0')}.${p.koszt_pracy_miesiac.rok})`} value={zl(p.koszt_pracy_miesiac.kwota)} icon="users" />
            </div>
          </section>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[['Gotówka', 'gotowka'], ['Karta', 'karta'], ['Przelew', 'przelew'],
              ...(cfg?.impreza_osobne_rozliczenie !== false ? [['Impreza', 'impreza']] : [])].map(([l, k]) => (
              <div key={k} className="rounded-xl border border-line bg-surface px-4 py-3">
                <div className="text-xs text-muted">{l}</div>
                <div className="font-display font-bold text-ink">{zl(p.przychod[k])}</div>
              </div>
            ))}
          </div>

          {p.przychod.dzienny.length > 0 && (
            <figure aria-labelledby="pulpit-przychod-dzienny-title">
              <figcaption id="pulpit-przychod-dzienny-title" className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                Przychód dzienny
              </figcaption>
              <div
                aria-hidden="true"
                className="flex h-40 items-end gap-1 overflow-x-auto rounded-xl border border-line bg-surface p-3"
              >
                {p.przychod.dzienny.map((d) => (
                  <div key={d.data} className="flex min-w-[8px] flex-1 flex-col items-center">
                    <div className="w-full rounded-t bg-mint" style={{ height: `${Math.round((d.przychod / maxPrzychod) * 100)}%`, minHeight: d.przychod > 0 ? '4px' : '0' }} />
                  </div>
                ))}
              </div>
              <details className="group mt-2">
                <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-muted transition hover:bg-white/[0.04] hover:text-ink [&::-webkit-details-marker]:hidden">
                  <Icon name="chevronDown" className="h-4 w-4 transition-transform duration-150 ease-snap group-open:rotate-180" />
                  Pokaż wartości dzienne
                </summary>
                <ul className="mt-1 grid gap-x-6 rounded-xl bg-white/[0.02] px-4 py-2 sm:grid-cols-2" aria-label="Wartości przychodu według dni">
                  {p.przychod.dzienny.map((d) => (
                    <li key={d.data} className="flex items-center justify-between gap-4 border-b border-line/60 py-2 text-sm last:border-0">
                      <time dateTime={d.data} className="text-muted">{dataKrotko(d.data)}</time>
                      <span className="font-semibold tabular-nums text-ink">{zl(d.przychod)}</span>
                    </li>
                  ))}
                </ul>
              </details>
            </figure>
          )}

          {p.rezerwacje.razem > 0 && (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Rezerwacje wg statusu</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(p.rezerwacje.wg_statusu).map(([s, n]) => (
                  <span key={s} className="rounded-full border border-line bg-surface-2 px-3 py-1.5 text-xs text-ink">{STATUS_L[s] || s}: <b>{n}</b></span>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-line bg-surface-2 p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Wynik poglądowy (przychód − rozchód − koszt pracy)</div>
            <div className={`font-display text-2xl font-bold ${p.wynik >= 0 ? 'text-mint' : 'text-danger'}`}>{zl(p.wynik)}</div>
          </div>
        </div>
      )}
    </section>
  )
}
