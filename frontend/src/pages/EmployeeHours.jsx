import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from '../components/ui/Toast'
import { godzinyHM, NAZWY_DNI, ddmmyyyy, zl, kolorStanowiska } from '../lib/format'

// Zakładka „Godziny": miesięczne podsumowanie przepracowanych godzin pracownika
// — suma u góry (HH:MM), podział na dni i na stanowiska (dane z RCP × opublikowany grafik).
export default function EmployeeHours() {
  const { toast } = useToast()
  const dzis = new Date()
  const [rok, setRok] = useState(dzis.getFullYear())
  const [miesiac, setMiesiac] = useState(dzis.getMonth() + 1) // 1-12
  const [dane, setDane] = useState(null)
  const [napiwki, setNapiwki] = useState(null)
  const [loading, setLoading] = useState(true)

  // Napiwki pracownika w tym miesiącu (suma + rozbicie na dni) — osobno, nie blokuje spinnera godzin.
  useEffect(() => {
    const mm = String(miesiac).padStart(2, '0')
    const ostatni = String(new Date(rok, miesiac, 0).getDate()).padStart(2, '0')
    api(`/me/napiwki?start=${rok}-${mm}-01&end=${rok}-${mm}-${ostatni}`).then(setNapiwki).catch(() => setNapiwki(null))
  }, [rok, miesiac])

  const etykietaMiesiaca = useMemo(
    () => new Intl.DateTimeFormat('pl-PL', { month: 'long', year: 'numeric' }).format(new Date(rok, miesiac - 1, 1)),
    [rok, miesiac],
  )

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setDane(await api(`/me/godziny?rok=${rok}&miesiac=${miesiac}`))
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

  // Portfel (roadmapa v2): zarobek na żywo + zaliczki dla wybranego miesiąca.
  const [portfel, setPortfel] = useState(null)
  const [kwotaZal, setKwotaZal] = useState('')
  const [busyZal, setBusyZal] = useState(false)
  const loadPortfel = useCallback(() => {
    api(`/me/portfel?rok=${rok}&miesiac=${miesiac}`).then(setPortfel).catch(() => setPortfel(null))
  }, [rok, miesiac])
  useEffect(() => { loadPortfel() }, [loadPortfel])
  const biezacyMiesiac = rok === dzis.getFullYear() && miesiac === dzis.getMonth() + 1

  const zlozWniosek = async () => {
    const kwota = parseFloat(kwotaZal)
    if (!kwota || kwota <= 0) { toast('Podaj kwotę zaliczki.', 'error'); return }
    setBusyZal(true)
    try {
      await api('/me/portfel/zaliczki', 'POST', { kwota })
      toast('Wniosek wysłany — manager dostał powiadomienie.', 'success')
      setKwotaZal(''); loadPortfel()
    } catch (e) { toast(e.message, 'error') } finally { setBusyZal(false) }
  }
  const wycofajWniosek = async (z) => {
    try { await api(`/me/portfel/zaliczki/${z.id}`, 'DELETE'); loadPortfel() }
    catch (e) { toast(e.message, 'error') }
  }

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

  const stanowiska = dane?.stanowiska || []
  const dni = dane?.dni || []
  const maxGodziny = Math.max(1, ...stanowiska.map((s) => s.godziny))
  const naPrzyszlosc = rok > dzis.getFullYear() || (rok === dzis.getFullYear() && miesiac >= dzis.getMonth() + 1)

  return (
    <div className="space-y-6">
      {/* Nawigacja miesiącem */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => przesunMiesiac(-1)}
          className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-[0.98]"
          aria-label="Poprzedni miesiąc"
        >
          <Icon name="chevronDown" className="h-4 w-4 rotate-90" />
        </button>
        <span className="font-display text-lg font-bold capitalize text-ink">{etykietaMiesiaca}</span>
        <button
          onClick={() => przesunMiesiac(1)}
          disabled={naPrzyszlosc}
          className="rounded-xl border border-line bg-white/[0.04] p-2.5 text-muted transition hover:text-ink active:scale-[0.98] disabled:opacity-30"
          aria-label="Następny miesiąc"
        >
          <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
        </button>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : (
        <>
          {/* Trwająca, niezakończona zmiana — „dziś jesteś na zmianie" (pulsująca kropka). */}
          {dane?.aktywna_zmiana && (
            <Card className="flex items-center gap-3 border-mint/30 bg-mint/[0.06] p-4">
              <span className="relative flex h-3 w-3 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
                <span className="relative inline-flex h-3 w-3 rounded-full bg-mint" />
              </span>
              <div className="min-w-0">
                <div className="text-sm font-bold text-ink">Zmiana w toku — dziś</div>
                <div className="text-xs text-muted">
                  Rozpoczęta o {dane.aktywna_zmiana.wejscie.slice(11, 16)} — godziny doliczą się po wybiciu wyjścia.
                </div>
              </div>
            </Card>
          )}

          {/* Najpierw odpowiedź na dwa najczęstsze pytania pracownika. */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Card className="p-6 text-center">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted">Łącznie w miesiącu</div>
              <div className="mt-1 font-display text-4xl font-bold text-ink tabular-nums sm:text-5xl">
                {godzinyHM(dane?.suma_godzin)}
              </div>
            </Card>
            <Card className="border-mint/30 bg-mint/[0.05] p-6 text-center">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted">Do wypłaty</div>
              <div className="mt-1 font-display text-4xl font-bold tabular-nums text-mint sm:text-5xl">
                {zl(dane?.do_wyplaty)}
              </div>
            </Card>
          </div>

          {/* Portfel: zarobek na żywo + zaliczki (roadmapa v2) */}
          {portfel && (
            <Card className="p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted">Zarobiłeś już w tym miesiącu</div>
                  <div className="mt-1 font-display text-3xl font-bold tabular-nums text-mint">{zl(portfel.zarobek)}</div>
                </div>
                {biezacyMiesiac && (
                  <div className="text-right text-xs text-muted">
                    Dostępna zaliczka: <span className="font-semibold text-ink">{zl(portfel.dostepna_zaliczka)}</span>
                    <span className="block text-muted/70">(do {portfel.limit_procent}% dotychczasowego zarobku)</span>
                  </div>
                )}
              </div>
              {biezacyMiesiac && portfel.dostepna_zaliczka > 0 && (
                <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                  <input
                    type="number" min="1" value={kwotaZal} onChange={(e) => setKwotaZal(e.target.value)}
                    placeholder="kwota zaliczki (zł)"
                    className="w-full min-w-0 flex-1 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted/50 focus:border-mint/60 focus:ring-2 focus:ring-mint/20"
                  />
                  <button type="button" onClick={zlozWniosek} disabled={busyZal}
                          className="min-h-11 w-full shrink-0 rounded-xl bg-mint px-4 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-50 sm:w-auto">
                    Poproś o zaliczkę
                  </button>
                </div>
              )}
              {portfel.zaliczki.length > 0 && (
                <div className="mt-4 space-y-1.5">
                  {portfel.zaliczki.map((z) => (
                    <div key={z.id} className="flex items-center gap-3 text-sm">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        z.status === 'zaakceptowana' ? 'bg-success/15 text-success'
                        : z.status === 'odrzucona' ? 'bg-danger/15 text-danger' : 'bg-white/[0.06] text-muted'}`}>
                        {z.status}
                      </span>
                      <span className="tabular-nums text-ink">{zl(z.kwota)}</span>
                      <span className="flex-1 text-xs text-muted">{(z.wniosek_at || '').slice(0, 10)}</span>
                      {z.status === 'oczekuje' && (
                        <button onClick={() => wycofajWniosek(z)} className="text-xs text-muted underline-offset-2 transition hover:text-ink hover:underline">
                          wycofaj
                        </button>
                      )}
                    </div>
                  ))}
                  <p className="pt-1 text-xs text-muted/70">Zaakceptowane zaliczki są potrącane z wypłaty tego miesiąca.</p>
                </div>
              )}
            </Card>
          )}

          {/* Napiwki miesiąca — suma + rozbicie na dni (jeśli są). */}
          {napiwki && napiwki.suma > 0 && (
            <Card className="border-lemon/30 bg-lemon/[0.05] p-4 sm:p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
                  <Icon name="sparkles" className="h-4 w-4 text-lemon" /> Napiwki w miesiącu
                </div>
                <div className="font-display text-xl font-bold tabular-nums text-lemon">{zl(napiwki.suma)}</div>
              </div>
              <div className="mt-2 space-y-0.5">
                {napiwki.dni.map((d) => (
                  <div key={d.data} className="flex items-center justify-between border-b border-line/60 py-1.5 text-sm last:border-0">
                    <span className="text-muted">{ddmmyyyy(d.data)}</span>
                    <span className="font-mono font-bold tabular-nums text-ink">{zl(d.kwota)}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {(dane?.suma_godzin ?? 0) === 0 ? (
            <Card className="p-8 text-center text-sm text-muted">
              Brak zarejestrowanych godzin w tym miesiącu. Godziny pojawią się po odbiciach RCP.
            </Card>
          ) : (
            <>
              {/* Podział na dni — w jakim dniu ile przepracowano */}
              {dni.length > 0 && (
                <Card className="p-4 sm:p-5">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Według dni</div>
                  <div className="space-y-0.5">
                    {dni.map((d) => (
                      <div key={d.data} className="flex items-center justify-between border-b border-line/60 py-2 last:border-0">
                        <div className="flex items-baseline gap-2">
                          <span className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(d.data).getDay()]}</span>
                          <span className="text-xs text-muted">{ddmmyyyy(d.data)}</span>
                        </div>
                        <span className="font-mono font-bold tabular-nums text-ink">{godzinyHM(d.godziny)}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Rozbicie na stanowiska — każde w swoim kolorze, prosto „Sala: 12:00" */}
              {stanowiska.length > 0 && (
                <Card className="p-4 sm:p-5">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Według stanowisk</div>
                  <div className="space-y-3.5">
                    {stanowiska.map((s) => {
                      const kolor = kolorStanowiska(s.stanowisko)
                      return (
                        <div key={s.stanowisko}>
                          <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                            <span className="flex min-w-0 items-center gap-2">
                              <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: kolor }} />
                              <span className="truncate font-semibold text-ink">{s.stanowisko}:</span>
                              <span className="shrink-0 font-mono font-bold tabular-nums text-ink">{godzinyHM(s.godziny)}</span>
                            </span>
                            {s.kwota > 0 && <span className="shrink-0 text-xs font-semibold tabular-nums text-mint">{zl(s.kwota)}</span>}
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                            <div
                              className="h-full rounded-full transition-[width] duration-500"
                              style={{ width: `${(s.godziny / maxGodziny) * 100}%`, background: kolor }}
                            />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </Card>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
