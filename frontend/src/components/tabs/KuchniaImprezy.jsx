import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { WeekSelect } from '../ui/WeekSelect'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'

// Imprezy dla pracownika KUCHNI — podgląd operacyjny do planowania pracy.
// PRYWATNOŚĆ: bez nazwy klienta — dane z /api/me/imprezy (tylko sala, godzina,
// liczba osób), spójnie z tym, co przy dyspozycjach widzi pracownik obsługi.
const pusta = (v) => !v || v === 'None' || v === 'Brak'
const fmtG = (g) => {
  const m = String(g || '').match(/^(\d{1,2}):(\d{2})/)
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : ''
}

export default function KuchniaImprezy() {
  const { week, biezacy, setWeek } = useData()
  const { toast } = useToast()
  const [imprezy, setImprezy] = useState([])
  const [loading, setLoading] = useState(true)

  // Kuchnia patrzy na BIEŻĄCY tydzień (nie przyszły jak dyspozycje).
  useEffect(() => { setWeek(biezacy) }, [biezacy, setWeek])

  const [s, e] = week.split('|')

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setImprezy(await api(`/me/imprezy?start=${s}&end=${e}`))
    } catch (err) {
      if (!silent) toast(err.message, 'error')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [s, e, toast])

  useEffect(() => { load() }, [load])

  // Live: ciche odświeżanie co 60 s, gdy karta jest widoczna.
  useEffect(() => {
    const id = setInterval(() => { if (document.visibilityState === 'visible') load(true) }, 60000)
    return () => clearInterval(id)
  }, [load])

  return (
    <Card className="mx-auto max-w-3xl p-6 sm:p-8">
      <div className="mb-5">
        <WeekSelect />
      </div>
      <SectionHeader title="Imprezy" subtitle={`Imprezy w tygodniu ${ddmmyyyy(s)} — ${ddmmyyyy(e)}`} />

      {loading ? (
        <div className="grid place-items-center py-12">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : imprezy.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] p-8 text-center text-sm text-muted">
          Brak imprez na ten tydzień.
        </div>
      ) : (
        <div className="space-y-3">
          {imprezy.map((imp) => (
            <div key={imp.id} className="rounded-2xl border border-line bg-white/[0.02] p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 font-bold text-ink">
                  {!pusta(imp.sala) ? (
                    <>
                      <Icon name="pin" className="h-3.5 w-3.5 text-mint" /> Sala {imp.sala}
                    </>
                  ) : (
                    'Impreza'
                  )}
                </span>
                <span className="shrink-0 font-mono text-xs font-semibold text-muted">{ddmmyyyy(imp.data)}</span>
              </div>
              <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
                {fmtG(imp.godzina) && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-white/[0.06] px-2.5 py-1 font-mono font-semibold text-ink">
                    <Icon name="clock" className="h-3 w-3" /> {fmtG(imp.godzina)}
                  </span>
                )}
                {imp.liczba_osob > 0 && (
                  <span className="inline-flex items-center gap-1 text-muted">
                    <Icon name="users" className="h-3.5 w-3.5" /> <span className="font-bold text-ink">{imp.liczba_osob}</span> os.
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
