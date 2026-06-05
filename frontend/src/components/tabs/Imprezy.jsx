import { useState, useEffect, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Banner } from '../ui/Banner'
import { Icon } from '../../lib/icons'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useData } from '../../context/DataContext'
import { useToast } from '../ui/Toast'
import { ddmmyyyy } from '../../lib/format'

// Baza imprez z serwera NAS. Lista per tydzień + synchronizacja (skan plików .xlsx).
const pusta = (v) => !v || v === 'None' || v === 'Brak'

export default function Imprezy() {
  const { week } = useData()
  const { toast } = useToast()
  const [imprezy, setImprezy] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  const pobierz = useCallback(async () => {
    const [s, e] = week.split('|')
    setLoading(true)
    try {
      setImprezy(await api(`/imprezy?start=${s}&end=${e}`))
    } catch (err) {
      toast(`Błąd pobierania imprez: ${err.message}`, 'error')
      setImprezy([])
    } finally {
      setLoading(false)
    }
  }, [week, toast])

  useEffect(() => {
    pobierz()
  }, [pobierz])

  const synchronizuj = async () => {
    const [s, e] = week.split('|')
    setSyncing(true)
    try {
      const data = await api(`/imprezy/sync?start=${s}&end=${e}`, 'POST')
      toast(`Synchronizacja OK — dodano ${data.dodano}, zaktualizowano ${data.zaktualizowano}, błędy ${data.bledy}.`, 'success')
      await pobierz()
    } catch (err) {
      toast(`Błąd synchronizacji: ${err.message}`, 'error')
    } finally {
      setSyncing(false)
    }
  }

  const [s, e] = week.split('|')

  return (
    <Card className="mx-auto max-w-3xl p-6 sm:p-8">
      <SectionHeader title="Baza Imprez (Ustalone)" subtitle={`Skan plików .xlsx dla tygodnia ${ddmmyyyy(s)} — ${ddmmyyyy(e)}`}>
        <Button onClick={synchronizuj} disabled={syncing}>
          {syncing ? <Spinner className="h-4 w-4" /> : <Icon name="refresh" className="h-4 w-4" />}
          {syncing ? 'Skanowanie…' : 'Synchronizuj NAS'}
        </Button>
      </SectionHeader>

      <Banner variant="warn" className="mb-6">
        Upewnij się, że dysk z plikami imprez (NAS) jest podłączony w Finderze, zanim klikniesz synchronizację.
      </Banner>

      {/* Karty zamiast tabeli — czytelne na mobile, nic się nie ucina. */}
      {loading ? (
        <div className="grid place-items-center py-12">
          <Spinner className="h-6 w-6 text-muted" />
        </div>
      ) : imprezy.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] p-8 text-center text-sm text-muted">
          Brak imprez na ten tydzień. Kliknij „Synchronizuj NAS”.
        </div>
      ) : (
        <div className="space-y-3">
          {imprezy.map((imp, i) => (
            <div
              key={imp.id}
              className="animate-fade-up rounded-xl border border-line bg-white/[0.02] p-4 transition hover:bg-white/[0.04]"
              style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="font-bold text-ink">{imp.klient}</span>
                <span className="shrink-0 font-mono text-xs font-semibold text-muted">{ddmmyyyy(imp.data)}</span>
              </div>
              <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
                {!pusta(imp.sala) && (
                  <span className="inline-flex items-center gap-1 rounded-lg border border-mint/20 bg-mint/10 px-2.5 py-1 font-mono font-bold text-mint">
                    <Icon name="pin" className="h-3 w-3" /> {imp.sala}
                  </span>
                )}
                {!pusta(imp.godzina) && (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-white/[0.06] px-2.5 py-1 font-mono font-semibold text-ink">
                    <Icon name="clock" className="h-3 w-3" /> {imp.godzina}
                  </span>
                )}
                {imp.liczba_osob > 0 && (
                  <span className="inline-flex items-center gap-1 text-muted">
                    <Icon name="users" className="h-3.5 w-3.5" /> <span className="font-bold text-ink">{imp.liczba_osob}</span> os.
                  </span>
                )}
                {pusta(imp.sala) && pusta(imp.godzina) && !(imp.liczba_osob > 0) && (
                  <span className="italic text-muted">Brak szczegółów</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
