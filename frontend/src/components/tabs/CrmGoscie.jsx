import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// CRM gości — historia rezerwacji, scoring no-show, VIP. Czysta agregacja z /api/crm/goscie (zero zapisu).
const RYZYKO = {
  wysokie: 'bg-danger/15 text-danger',
  srednie: 'bg-amber-400/15 text-amber-300',
  niskie: 'bg-white/10 text-muted',
}

export default function CrmGoscie() {
  const { toast } = useToast()
  const [goscie, setGoscie] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try { setGoscie(await api('/crm/goscie')) }
    catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  if (loading) {
    return <Card className="p-8"><div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div></Card>
  }

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader title="Goście (CRM)" subtitle="Historia rezerwacji, ryzyko no-show i status VIP — z danych rezerwacji." />
      {!goscie || goscie.length === 0 ? (
        <div className="mt-6 rounded-xl border border-line bg-surface-2 p-8 text-center text-sm text-muted">
          Brak danych gości — pojawią się po pierwszych rezerwacjach stolików.
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-3 font-semibold">Gość</th>
                <th className="py-2 pr-3 font-semibold">Kontakt</th>
                <th className="py-2 pr-3 text-right font-semibold">Wizyt</th>
                <th className="py-2 pr-3 text-right font-semibold">Odbyte</th>
                <th className="py-2 pr-3 text-right font-semibold">No-show</th>
                <th className="py-2 pr-3 font-semibold">Ryzyko</th>
                <th className="py-2 pr-3 font-semibold">Ostatnia wizyta</th>
              </tr>
            </thead>
            <tbody>
              {goscie.map((g) => (
                <tr key={g.klucz} className="border-b border-line/60">
                  <td className="py-2.5 pr-3">
                    <span className="font-semibold text-ink">{g.nazwisko || '—'}</span>
                    {g.vip && <span className="ml-2 rounded-full bg-accent-gradient px-2 py-0.5 text-[10px] font-bold text-bg">VIP</span>}
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{g.telefon || g.email || '—'}</td>
                  <td className="py-2.5 pr-3 text-right text-ink">{g.wizyt}</td>
                  <td className="py-2.5 pr-3 text-right text-ink">{g.odbyte}</td>
                  <td className="py-2.5 pr-3 text-right text-ink">
                    {g.no_show}{g.no_show > 0 && <span className="text-muted"> ({g.no_show_proc}%)</span>}
                  </td>
                  <td className="py-2.5 pr-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${RYZYKO[g.ryzyko] || RYZYKO.niskie}`}>{g.ryzyko}</span>
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{g.ostatnia_data}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
