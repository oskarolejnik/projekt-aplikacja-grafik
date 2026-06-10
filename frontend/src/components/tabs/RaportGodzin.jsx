import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { godzinyHM, zl, kolorStanowiska, ddmmyyyy } from '../../lib/format'
import { useAuth } from '../../context/AuthContext'

// Raport godzin (admin): miesięczne podsumowanie przepracowanych godzin wszystkich
// pracowników z rozbiciem na stanowiska (RCP × opublikowany grafik). Tylko odczyt.
// Dane: GET /api/raporty/godziny?rok=&miesiac= (raporty.raport_godzin_miesiac).
export default function RaportGodzin() {
  const { toast } = useToast()
  const { isAdmin } = useAuth()
  const dzis = new Date()
  const [rok, setRok] = useState(dzis.getFullYear())
  const [miesiac, setMiesiac] = useState(dzis.getMonth() + 1) // 1-12
  const [dane, setDane] = useState(null)
  const [loading, setLoading] = useState(true)

  const etykietaMiesiaca = useMemo(
    () => new Intl.DateTimeFormat('pl-PL', { month: 'long', year: 'numeric' }).format(new Date(rok, miesiac - 1, 1)),
    [rok, miesiac],
  )

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setDane(await api(`/raporty/godziny?rok=${rok}&miesiac=${miesiac}`))
    } catch (e) {
      if (!silent) {
        toast(e.message, 'error')
        setDane(null)
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [rok, miesiac, toast])

  useEffect(() => {
    load()
  }, [load])

  // Live: ciche odświeżanie co 20 s (bez spinnera), tylko gdy karta jest widoczna.
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(true)
    }, 20000)
    return () => clearInterval(id)
  }, [load])

  const przesunMiesiac = (delta) => {
    let m = miesiac + delta
    let r = rok
    if (m < 1) { m = 12; r -= 1 }
    if (m > 12) { m = 1; r += 1 }
    setMiesiac(m)
    setRok(r)
  }

  const pracownicy = dane?.pracownicy || []
  const niedopasowani = dane?.niedopasowani_rcp || []
  const duzeCiecia = dane?.duze_ciecia || []   // >1h (admin + szef)
  const maleCiecia = dane?.male_ciecia || []   // 10 min–1h (admin + szef)
  const pozaGrafikiem = isAdmin ? (dane?.poza_grafikiem || []) : []  // godziny nieprzypisane — tylko admin
  const sumaWszystkich = useMemo(() => pracownicy.reduce((acc, p) => acc + (p.suma_godzin || 0), 0), [pracownicy])
  const sumaWyplat = useMemo(() => pracownicy.reduce((acc, p) => acc + (p.do_wyplaty || 0), 0), [pracownicy])
  const zaoszczedzone = dane?.zaoszczedzone || { godziny: 0, kwota: 0 }
  const naPrzyszlosc = rok > dzis.getFullYear() || (rok === dzis.getFullYear() && miesiac >= dzis.getMonth() + 1)

  const stanowiskaPodsum = dane?.stanowiska_podsumowanie || []
  const maxStan = Math.max(1, ...stanowiskaPodsum.map((s) => s.godziny))
  const kuchnia = useMemo(() => pracownicy.filter((p) => p.dzial === 'kuchnia'), [pracownicy])
  const techniczni = useMemo(() => pracownicy.filter((p) => p.dzial === 'techniczny'), [pracownicy])
  const obsluga = useMemo(() => pracownicy.filter((p) => p.dzial !== 'kuchnia' && p.dzial !== 'techniczny'), [pracownicy])
  const sumaDzialu = (lista) => ({
    godziny: lista.reduce((a, p) => a + (p.suma_godzin || 0), 0),
    kwota: lista.reduce((a, p) => a + (p.do_wyplaty || 0), 0),
  })

  // Karta jednego pracownika (rozbicie na stanowiska — każde w swoim kolorze). Wspólna dla kuchni i obsługi.
  const kartaPracownika = (p) => {
    const maxG = Math.max(1, ...p.stanowiska.map((s) => s.godziny))
    return (
      <div key={p.pracownik_id} className="rounded-xl border border-line bg-white/[0.02] p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="min-w-0 truncate font-semibold text-ink">{p.pracownik}</span>
          <div className="flex shrink-0 items-baseline gap-3">
            <span className="font-display font-bold tabular-nums text-ink">{godzinyHM(p.suma_godzin)}</span>
            <span className="font-display font-bold tabular-nums text-mint">{zl(p.do_wyplaty)}</span>
          </div>
        </div>
        <div className="space-y-2">
          {p.stanowiska.map((s) => {
            const kolor = kolorStanowiska(s.stanowisko)
            return (
              <div key={s.stanowisko} className="flex items-center gap-3">
                <span className="flex w-28 shrink-0 items-center gap-1.5 text-xs text-muted" title={s.stanowisko}>
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: kolor }} />
                  <span className="truncate">{s.stanowisko}{s.stawka > 0 ? ` · ${zl(s.stawka)}/h` : ''}</span>
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full" style={{ width: `${(s.godziny / maxG) * 100}%`, background: kolor }} />
                </div>
                <span className="w-12 shrink-0 text-right font-mono text-xs font-bold text-ink tabular-nums">{godzinyHM(s.godziny)}</span>
                <span className="w-16 shrink-0 text-right text-xs font-semibold tabular-nums text-mint">{s.kwota > 0 ? zl(s.kwota) : ''}</span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // Dział jako lista rozwijana (nagłówek = osoby · godziny · wypłata). Karty po rozwinięciu.
  const sekcjaDzialu = (tytul, lista) =>
    lista.length > 0 && (() => {
      const s = sumaDzialu(lista)
      return (
        <details className="group rounded-xl border border-line bg-white/[0.02]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 outline-none [&::-webkit-details-marker]:hidden">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {tytul} · {lista.length} os. · {godzinyHM(s.godziny)} · {zl(s.kwota)}
            </span>
            <Icon name="chevronDown" className="h-4 w-4 shrink-0 text-muted transition group-open:rotate-180" />
          </summary>
          <div className="space-y-3 border-t border-line p-3">
            {lista.map(kartaPracownika)}
          </div>
        </details>
      )
    })()

  // Cięcia godzin jako lista ROZWIJANA — nagłówek z liczbą, szczegóły po rozwinięciu. Admin i szef.
  const bannerCiec = (lista, tytul, podpowiedz, wariant) =>
    lista.length > 0 && (
      <details className={`group mb-6 rounded-xl border ${wariant === 'warn' ? 'border-lemon/30 bg-lemon/[0.05]' : 'border-line bg-white/[0.02]'}`}>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 outline-none [&::-webkit-details-marker]:hidden">
          <span className={`text-sm font-semibold ${wariant === 'warn' ? 'text-lemon' : 'text-ink'}`}>{tytul} — {lista.length}</span>
          <Icon name="chevronDown" className="h-4 w-4 shrink-0 text-muted transition group-open:rotate-180" />
        </summary>
        <div className="border-t border-line/60 px-4 py-3">
          <p className="text-xs text-muted">{podpowiedz}</p>
          <ul className="mt-2 space-y-1.5 text-xs">
            {lista.map((c, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                <span className="font-semibold text-ink">{c.pracownik}</span>
                <span className="text-muted">{ddmmyyyy(c.data)}{c.stanowisko ? ` · ${c.stanowisko}` : ''}</span>
                <span className="font-mono text-muted">wszedł {c.wejscie ?? '—'} / plan {c.planowane ?? '—'}</span>
                <span className="ml-auto font-mono font-bold text-coral">−{godzinyHM(c.godziny_uciete)}</span>
              </li>
            ))}
          </ul>
        </div>
      </details>
    )

  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink">Raport godzin</h2>
          <p className="mt-1 text-sm text-muted">Przepracowane godziny (RCP) z podziałem na stanowiska z opublikowanego grafiku.</p>
        </div>
        {/* Nawigacja miesiącem */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => przesunMiesiac(-1)}
            className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-95"
            aria-label="Poprzedni miesiąc"
          >
            <Icon name="chevronDown" className="h-4 w-4 rotate-90" />
          </button>
          <span className="min-w-[150px] text-center font-display text-base font-bold capitalize text-ink">{etykietaMiesiaca}</span>
          <button
            onClick={() => przesunMiesiac(1)}
            disabled={naPrzyszlosc}
            className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-95 disabled:opacity-30"
            aria-label="Następny miesiąc"
          >
            <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <>
          {/* Na zmianie TERAZ (live) — niezakończone odbicia. Odświeża się co 20 s. */}
          {dane?.na_zmianie?.length > 0 && (
            <div className="mb-6 rounded-xl border border-mint/30 bg-mint/[0.05] p-4">
              <div className="mb-3 flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-mint" />
                </span>
                <span className="text-sm font-bold text-ink">Na zmianie teraz ({dane.na_zmianie.length})</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {dane.na_zmianie.map((z, i) => (
                  <span key={i} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white/[0.03] px-2.5 py-1 text-xs">
                    <span className="font-semibold text-ink">{z.pracownik}</span>
                    <span className="font-mono text-muted">od {z.wejscie.slice(11, 16)}</span>
                    {!z.dopasowany && <span className="rounded bg-lemon/15 px-1 text-[10px] font-bold text-lemon">niedopasowany</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Pasek podsumowania zbiorczego */}
          <div className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-2 rounded-xl border border-line bg-white/[0.02] px-5 py-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Łącznie (wszyscy)</div>
              <div className="font-display text-2xl font-bold text-gradient tabular-nums">
                {godzinyHM(sumaWszystkich)}
              </div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Pracownicy z godzinami</div>
              <div className="font-display text-2xl font-bold text-ink tabular-nums">{pracownicy.length}</div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Do wypłaty (wszyscy)</div>
              <div className="font-display text-2xl font-bold tabular-nums text-mint">{zl(sumaWyplat)}</div>
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">Zaoszczędzone (wg grafiku)</div>
              <div className="font-display text-2xl font-bold tabular-nums text-coral">
                {godzinyHM(zaoszczedzone.godziny)} · {zl(zaoszczedzone.kwota)}
              </div>
            </div>
          </div>

          {/* Cięcia godzin (>10 min): duże (>1h, zwykle zmiana w grafiku) + małe (10 min–1h). TYLKO admin. */}
          {bannerCiec(duzeCiecia, 'Duże cięcia godzin (powyżej 1h)',
            'Zwykle błędny wpis w grafiku (faktyczna zmiana inna niż wpisana) — sprawdź godzinę zmiany:', 'warn')}
          {bannerCiec(maleCiecia, 'Małe cięcia godzin (10 min – 1h)',
            'Drobne wejścia przed grafikiem — zwykle normalne:', 'info')}

          {/* Godziny nieprzypisane do grafiku — lista rozwijana, TYLKO admin */}
          {pozaGrafikiem.length > 0 && (
            <details className="group mb-6 rounded-xl border border-line bg-white/[0.02]">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 outline-none [&::-webkit-details-marker]:hidden">
                <span className="text-sm font-semibold text-ink">Godziny poza grafikiem — {pozaGrafikiem.length}</span>
                <Icon name="chevronDown" className="h-4 w-4 shrink-0 text-muted transition group-open:rotate-180" />
              </summary>
              <div className="border-t border-line/60 px-4 py-3">
                <p className="text-xs text-muted">Godziny z RCP nieprzypisane do grafiku — pracownik odbił się, ale nie ma go w grafiku tego dnia (lub tydzień nieopublikowany):</p>
                <ul className="mt-2 space-y-1.5 text-xs">
                  {pozaGrafikiem.map((p, i) => (
                    <li key={i} className="flex items-center justify-between gap-3">
                      <span className="font-semibold text-ink">{p.pracownik}</span>
                      <span className="font-mono font-bold tabular-nums text-ink">{godzinyHM(p.godziny)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </details>
          )}

          {pracownicy.length === 0 ? (
            <Card className="p-8 text-center text-sm text-muted">
              Brak zarejestrowanych godzin w tym miesiącu. Godziny pojawią się po odbiciach RCP
              i opublikowaniu grafiku.
            </Card>
          ) : (
            <div className="space-y-6">
              {/* Koszt i godziny wg stanowisk (sumarycznie, wszyscy) — każde stanowisko w swoim kolorze */}
              {stanowiskaPodsum.length > 0 && (
                <div className="rounded-xl border border-line bg-white/[0.02] p-4">
                  <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted">Koszt wg stanowisk</div>
                  <div className="space-y-2.5">
                    {stanowiskaPodsum.map((s) => {
                      const kolor = kolorStanowiska(s.stanowisko)
                      return (
                        <div key={s.stanowisko} className="flex items-center gap-3 text-sm">
                          <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: kolor }} />
                          <span className="w-28 shrink-0 truncate font-semibold text-ink" title={s.stanowisko}>{s.stanowisko}</span>
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                            <div className="h-full rounded-full" style={{ width: `${(s.godziny / maxStan) * 100}%`, background: kolor }} />
                          </div>
                          <span className="w-12 shrink-0 text-right font-mono text-xs font-bold text-ink tabular-nums">{godzinyHM(s.godziny)}</span>
                          <span className="w-16 shrink-0 text-right text-xs font-semibold tabular-nums text-mint">{s.kwota > 0 ? zl(s.kwota) : ''}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Działy jako listy rozwijane (nagłówek = osoby · godziny · wypłata; sort malejąco z backendu) */}
              {sekcjaDzialu('Kuchnia', kuchnia)}
              {sekcjaDzialu('Obsługa', obsluga)}
              {sekcjaDzialu('Techniczni', techniczni)}
            </div>
          )}

          {/* Odbicia RCP, których nie dopasowano do konta pracownika */}
          {niedopasowani.length > 0 && (
            <Banner variant="warn" className="mt-6">
              <div className="font-semibold">Niedopasowane odbicia RCP ({niedopasowani.length})</div>
              <p className="mt-1 text-xs">
                Te godziny nie zostały przypisane do żadnego konta pracownika (brak powiązania imię/nazwisko ↔ konto):
              </p>
              <ul className="mt-2 space-y-0.5 text-xs">
                {niedopasowani.map((n) => (
                  <li key={n.imie_nazwisko} className="flex justify-between gap-3">
                    <span>{n.imie_nazwisko || '(brak nazwiska)'}</span>
                    <span className="font-mono font-bold tabular-nums">{godzinyHM(n.godziny)}</span>
                  </li>
                ))}
              </ul>
            </Banner>
          )}
        </>
      )}
    </Card>
  )
}
