import { useEffect, useState, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'

// Antyfraud POS (roadmapa v2, TOP 3): storna/rabaty/anulacje z Gastro per kelner,
// porównane do reszty zespołu. FLAGI to zaproszenie do spokojnej rozmowy, nie oskarżenie —
// odstające liczby miewają niewinne przyczyny (nowy pracownik, awaria drukarki, imprezy).

const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const iso = (d) => d.toISOString().slice(0, 10)

export default function AntyfraudPos() {
  const { toast } = useToast()
  const [start, setStart] = useState(() => iso(new Date(Date.now() - 30 * 864e5)))
  const [end, setEnd] = useState(() => iso(new Date()))
  const [dane, setDane] = useState(null)
  const [loading, setLoading] = useState(true)
  const [aiBusy, setAiBusy] = useState(false)

  const load = useCallback(async (zAi = false) => {
    zAi ? setAiBusy(true) : setLoading(true)
    try {
      const w = await api(`/antyfraud/podsumowanie?start=${start}&end=${end}${zAi ? '&ai=1' : ''}`)
      setDane(w)
      if (zAi && !w.ai) toast('AI niedostępne — ustaw ANTHROPIC_API_KEY w środowisku backendu.', 'info')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setLoading(false); setAiBusy(false)
    }
  }, [start, end, toast])

  useEffect(() => { load() }, [load])

  const fld = 'rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink outline-none transition focus:border-mint/60 focus:ring-2 focus:ring-mint/20'
  const flagi = dane?.kelnerzy?.filter((k) => k.flaga).length || 0

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Antyfraud POS — storna i rabaty"
        subtitle={dane?.zespol?.zdarzen
          ? `${dane.zespol.zdarzen} zdarzeń · ${dane.zespol.osob} os. · ${flagi ? `${flagi} do rozmowy` : 'zespół w normie'}`
          : 'Porównanie stornowań każdego kelnera do reszty zespołu.'}
      >
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={fld} aria-label="Od" />
        <span className="text-muted">—</span>
        <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={fld} aria-label="Do" />
        {dane?.ai_dostepne && (
          <Button variant="accent" onClick={() => load(true)} disabled={aiBusy}>
            {aiBusy ? <Spinner className="h-4 w-4" /> : <Icon name="sparkles" className="h-4 w-4" />}
            Podsumowanie AI
          </Button>
        )}
      </SectionHeader>

      {dane?.ai && (
        <Card className="p-6">
          <div className="field-label">Podsumowanie tygodnia (AI)</div>
          <p className="mt-2 text-sm leading-relaxed text-ink">{dane.ai}</p>
        </Card>
      )}

      <Card className="p-0">
        {loading ? (
          <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
        ) : !dane?.kelnerzy?.length ? (
          <div className="px-6 py-12 text-center">
            <p className="text-sm text-muted">Brak danych o stornach w tym okresie.</p>
            <p className="mt-2 text-xs text-muted/70">
              Dane wypycha agent lokalny z POS Gastro — włącz sekcję STORNA w <code className="text-ink">agent_rcp.env</code>.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-5 py-3 font-semibold">Kelner</th>
                  <th className="px-3 py-3 text-right font-semibold">Storna</th>
                  <th className="px-3 py-3 text-right font-semibold">Rabaty</th>
                  <th className="px-3 py-3 text-right font-semibold">Anulacje</th>
                  <th className="px-3 py-3 text-right font-semibold">Suma</th>
                  <th className="px-5 py-3 font-semibold">Ocena</th>
                </tr>
              </thead>
              <tbody>
                {dane.kelnerzy.map((k) => (
                  <tr key={k.nazwa} className="border-b border-line last:border-b-0">
                    <td className="px-5 py-3 font-semibold text-ink">{k.nazwa}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-ink">{k.storno}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-ink">{k.rabat}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-ink">{k.anulacja}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-ink">{zl(k.suma)}</td>
                    <td className="px-5 py-3">
                      {k.flaga ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-danger/15 px-3 py-1 text-xs font-semibold text-danger" title={k.powod}>
                          <Icon name="warning" className="h-3.5 w-3.5" /> do rozmowy
                        </span>
                      ) : (
                        <span className="text-xs text-muted">w normie</span>
                      )}
                      {k.flaga && <div className="mt-1 text-xs text-muted">{k.powod}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="text-xs text-muted/70">
        Flaga = wynik ≥ 2× średniej reszty zespołu (min. 5 zdarzeń). To sygnał do spokojnej rozmowy —
        odstające liczby często mają niewinne przyczyny (szkolenie nowej osoby, awaria drukarki, duże imprezy).
      </p>
    </div>
  )
}
