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
    <Card className="max-w-5xl p-8">
      <SectionHeader title="Baza Imprez (Ustalone)" subtitle={`Skan plików .xlsx dla tygodnia ${ddmmyyyy(s)} — ${ddmmyyyy(e)}`}>
        <Button onClick={synchronizuj} disabled={syncing}>
          {syncing ? <Spinner className="h-4 w-4" /> : <Icon name="refresh" className="h-4 w-4" />}
          {syncing ? 'Skanowanie…' : 'Synchronizuj NAS'}
        </Button>
      </SectionHeader>

      <Banner variant="warn" className="mb-6">
        Upewnij się, że dysk z plikami imprez (NAS) jest podłączony w Finderze, zanim klikniesz synchronizację.
      </Banner>

      <div className="overflow-hidden rounded-xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-5 py-4 font-semibold">Data</th>
              <th className="px-5 py-4 font-semibold">Nazwa klienta</th>
              <th className="px-5 py-4 font-semibold">Sala</th>
              <th className="px-5 py-4 font-semibold">Godzina</th>
              <th className="px-5 py-4 font-semibold">Liczba osób</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-muted">
                  <Spinner className="mx-auto h-5 w-5" />
                </td>
              </tr>
            ) : imprezy.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-sm text-muted">
                  Brak imprez na ten tydzień. Kliknij „Synchronizuj NAS”.
                </td>
              </tr>
            ) : (
              imprezy.map((imp) => (
                <tr key={imp.id} className="transition hover:bg-white/[0.02]">
                  <td className="px-5 py-4">
                    <span className="font-semibold text-ink">{ddmmyyyy(imp.data)}</span>
                  </td>
                  <td className="px-5 py-4 font-bold text-ink">{imp.klient}</td>
                  <td className="px-5 py-4">
                    {pusta(imp.sala) ? (
                      <span className="italic text-muted">Brak</span>
                    ) : (
                      <span className="inline-block rounded-lg border border-mint/20 bg-mint/10 px-2.5 py-1 font-mono text-xs font-bold text-mint">
                        {imp.sala}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-4">
                    {pusta(imp.godzina) ? (
                      <span className="italic text-muted">Brak</span>
                    ) : (
                      <span className="inline-block rounded-lg bg-white/[0.06] px-3 py-1 font-semibold text-ink">{imp.godzina}</span>
                    )}
                  </td>
                  <td className="px-5 py-4 text-muted">
                    {imp.liczba_osob > 0 ? (
                      <span className="font-bold text-ink">{imp.liczba_osob} os.</span>
                    ) : (
                      <span className="italic text-muted">Brak</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
