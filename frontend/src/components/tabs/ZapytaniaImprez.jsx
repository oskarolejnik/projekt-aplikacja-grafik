import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { Card, SectionHeader } from '../ui/Card'
import { Hint } from '../ui/Hint'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'

// Skrzynka zapytań o imprezy (roadmapa v2, TOP 1): wklej treść maila z zapytaniem
// (wesele/komunia/firmowa) → parametry + wolne terminy z kalendarza + gotowy szkic
// odpowiedzi + karta terminu jednym kliknięciem. Pary rezerwują u tego, kto odpisze
// pierwszy — cel: odpowiedź w 2 minuty zamiast 2 dni.

const PRZYKLAD = 'np. „Dzień dobry, szukamy sali na wesele dla ok. 120 osób w sierpniu przyszłego roku, budżet ok. 250 zł od osoby. Czy mają Państwo wolne terminy? Pozdrawiam, Anna Nowak, tel. 601 234 567"'

export default function ZapytaniaImprez() {
  const { toast } = useToast()
  const [tresc, setTresc] = useState('')
  const [analiza, setAnaliza] = useState(null)     // odpowiedź POST /api/imprezy/zapytanie
  const [wybranaData, setWybranaData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [tworzenie, setTworzenie] = useState(false)
  const [aiAktywne, setAiAktywne] = useState(null)

  useEffect(() => {
    api('/imprezy/zapytanie/status').then((s) => setAiAktywne(s.ai)).catch(() => setAiAktywne(false))
  }, [])

  const analizuj = async () => {
    if (tresc.trim().length < 10) { toast('Wklej treść zapytania.', 'error'); return }
    setBusy(true); setAnaliza(null)
    try {
      const wynik = await api('/imprezy/zapytanie', 'POST', { tresc })
      setAnaliza(wynik)
      setWybranaData(wynik.karta?.data || null)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const kopiuj = async () => {
    try {
      await navigator.clipboard.writeText(analiza.szkic)
      toast('Szkic skopiowany — wklej do maila.', 'success')
    } catch {
      toast('Nie udało się skopiować — zaznacz tekst ręcznie.', 'error')
    }
  }

  const utworzTermin = async () => {
    if (!wybranaData) { toast('Wybierz termin z listy.', 'error'); return }
    setTworzenie(true)
    try {
      await api('/terminy', 'POST', { ...analiza.karta, data: wybranaData })
      toast(`Dodano termin ${wybranaData} do kalendarza imprez.`, 'success')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setTworzenie(false)
    }
  }

  const par = analiza?.parametry
  const chipy = par ? [
    par.typ && ['Typ', par.typ],
    par.liczba_osob && ['Goście', `${par.liczba_osob} os.`],
    par.budzet_od_osoby && ['Budżet', `${par.budzet_od_osoby} zł/os.`],
    par.telefon && ['Telefon', par.telefon],
    par.nazwisko && ['Klient', par.nazwisko],
  ].filter(Boolean) : []

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Zapytania o imprezy"
        subtitle="Wklej maila z zapytaniem — dostaniesz parametry, wolne terminy i gotowy szkic odpowiedzi."
      />

      <Card className="p-6">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Treść zapytania</span>
          <textarea
            value={tresc}
            onChange={(e) => setTresc(e.target.value)}
            rows={6}
            placeholder={PRZYKLAD}
            className="w-full min-w-0 resize-y rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm leading-relaxed text-ink outline-none transition placeholder:text-muted/50 focus:border-mint/60 focus:ring-2 focus:ring-mint/20"
          />
        </label>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-muted">
            {aiAktywne === null ? '' : aiAktywne
              ? 'AI aktywne — ekstrakcja i szkic generowane modelem.'
              : 'Tryb podstawowy (reguły + szablon). Klucz ANTHROPIC_API_KEY w środowisku włącza AI.'}
          </span>
          <Button onClick={analizuj} disabled={busy}>
            {busy ? <Spinner className="h-4 w-4" /> : <Icon name="sparkles" className="h-4 w-4" />}
            Analizuj zapytanie
          </Button>
        </div>
      </Card>

      {analiza && (
        <>
          <Card className="p-6">
            <h3 className="font-display text-base font-semibold text-ink">Co wyczytano</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {chipy.length === 0 && <span className="text-sm text-muted">Niewiele — uzupełnij kartę ręcznie po utworzeniu.</span>}
              {chipy.map(([k, v]) => (
                <span key={k} className="rounded-full border border-line bg-white/[0.04] px-3 py-1.5 text-xs text-ink">
                  <span className="text-muted">{k}: </span>{v}
                </span>
              ))}
            </div>

            <h3 className="mt-6 font-display text-base font-semibold text-ink">Terminy (kalendarz imprez)</h3>
            {analiza.terminy.length === 0 ? (
              <p className="mt-2 text-sm text-muted">Nie rozpoznano terminu w zapytaniu — wybierz datę ręcznie po utworzeniu karty.</p>
            ) : (
              <div className="mt-3 flex flex-wrap gap-2">
                {analiza.terminy.map((t) => (
                  <button
                    key={t.data}
                    type="button"
                    disabled={!t.wolny}
                    onClick={() => setWybranaData(t.data)}
                    className={`rounded-xl px-3 py-2 text-sm font-semibold transition active:scale-[0.98] ${
                      !t.wolny
                        ? 'cursor-not-allowed border border-line bg-white/[0.02] text-muted/50 line-through'
                        : wybranaData === t.data
                          ? 'bg-mint text-bg'
                          : 'border border-line bg-white/[0.04] text-ink hover:bg-white/[0.08]'
                    }`}
                    title={t.wolny ? 'Wolny — kliknij, aby wybrać' : 'Zajęty'}
                  >
                    {t.data} · {t.dzien}
                  </button>
                ))}
              </div>
            )}
            <div className="mt-5 flex justify-end">
              <Button variant="accent" onClick={utworzTermin} disabled={tworzenie || !wybranaData}>
                {tworzenie ? <Spinner className="h-4 w-4" /> : <Icon name="calendar" className="h-4 w-4" />}
                Dodaj do kalendarza imprez
              </Button>
            </div>
          </Card>

          <Card className="p-6">
            <div className="flex items-center justify-between gap-3">
              <h3 className="flex items-center gap-1.5 font-display text-base font-semibold text-ink">
                Szkic odpowiedzi {analiza.ai ? '(AI)' : '(szablon)'}
                <Hint>Możesz edytować przed skopiowaniem — szkic to punkt startu, nie gotowa oferta.</Hint>
              </h3>
              <Button variant="ghost" size="sm" onClick={kopiuj}>
                <Icon name="clipboard" className="h-4 w-4" /> Kopiuj
              </Button>
            </div>
            <textarea
              value={analiza.szkic}
              onChange={(e) => setAnaliza((a) => ({ ...a, szkic: e.target.value }))}
              rows={12}
              className="mt-3 w-full min-w-0 resize-y rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm leading-relaxed text-ink outline-none transition focus:border-mint/60 focus:ring-2 focus:ring-mint/20"
            />
          </Card>
        </>
      )}
    </div>
  )
}
