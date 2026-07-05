import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Panel operatora (instancja-matka): przegląd wszystkich lokali-instancji z żywym stanem
// subskrypcji. Dane z GET /api/flota (matka odpytuje dzieci przez /api/instancja/puls).
const PAKIET_L = { free: 'Darmowy', basic: 'Basic', pro: 'Pro', premium: 'Premium', enterprise: 'Enterprise' }
const STATUS_KOLOR = {
  aktywna: 'bg-mint/15 text-mint', trial: 'bg-lemon/15 text-lemon',
  wygasla: 'bg-danger/15 text-danger', zawieszona: 'bg-danger/15 text-danger',
}

function Licznik({ label, value, accent }) {
  return (
    <div className="rounded-2xl border border-line bg-surface-2 p-5">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 font-display text-3xl font-bold ${accent || 'text-ink'}`}>{value}</div>
    </div>
  )
}

export default function Flota() {
  const { toast } = useToast()
  const [dane, setDane] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try { setDane(await api('/flota')) }
    catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  if (loading) {
    return <Card className="p-8"><div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div></Card>
  }
  if (!dane?.enabled) {
    return (
      <Card className="p-8">
        <SectionHeader title="Flota" subtitle="Panel operatora nad instancjami lokali." />
        <p className="mt-4 rounded-xl border border-line bg-white/[0.02] px-4 py-3 text-sm text-muted">
          Samoobsługowe zakładanie lokali jest wyłączone na tej instalacji
          (<code className="text-ink">PROVISIONING_ENABLED</code>). Panel floty jest dostępny na
          instancji-matce, która stawia i utrzymuje instancje lokali.
        </p>
      </Card>
    )
  }

  const p = dane.podsumowanie
  const wpisy = Object.entries(p.wg_pakietu).sort((a, b) => b[1] - a[1])

  return (
    <div className="space-y-5">
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Flota lokali" subtitle={`Instancje postawione przez tę instalację. ${dane.puls_dostepny ? 'Stan subskrypcji zaciągany na żywo.' : 'Ustaw FLEET_TOKEN, by widzieć żywy stan subskrypcji.'}`} />
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Licznik label="Instancji" value={`${p.instancji} / ${dane.limit}`} />
          <Licznik label="Aktywnych" value={p.aktywnych} accent="text-mint" />
          <Licznik label="Pakiety" value={wpisy.length} />
          <Licznik label="Wolne miejsca" value={Math.max(0, dane.limit - p.instancji)} />
        </div>
        {!!wpisy.length && (
          <div className="mt-4 flex flex-wrap gap-2">
            {wpisy.map(([tier, n]) => (
              <span key={tier} className="rounded-full border border-line bg-white/[0.03] px-3 py-1 text-xs text-muted">
                {PAKIET_L[tier] || tier}: <b className="text-ink">{n}</b>
              </span>
            ))}
          </div>
        )}
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Instancje" subtitle="Kto ma jaki pakiet, status subskrypcji i czy instancja działa." />
        <div className="mt-4 overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="bg-surface-2 text-[11px] uppercase tracking-wide text-muted">
                <th className="px-3 py-2 text-left font-bold">Lokal</th>
                <th className="px-3 py-2 text-left font-bold">Kontakt</th>
                <th className="px-3 py-2 text-left font-bold">Pakiet</th>
                <th className="px-3 py-2 text-left font-bold">Status</th>
                <th className="px-3 py-2 text-right font-bold">Konta</th>
                <th className="px-3 py-2 text-left font-bold">Założony</th>
                <th className="px-3 py-2 text-center font-bold">Stan</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {dane.instancje.length === 0 && (
                <tr><td colSpan={8} className="px-3 py-4 text-center text-muted">Brak instancji — pojawią się tu po pierwszym samoobsługowym założeniu lokalu.</td></tr>
              )}
              {dane.instancje.map((w) => {
                const puls = w.puls
                const tier = puls?.tier || w.tier
                return (
                  <tr key={w.slug} className="border-t border-line/60">
                    <td className="px-3 py-2 font-semibold text-ink">{puls?.nazwa_lokalu || w.nazwa}
                      <span className="ml-1 text-xs font-normal text-muted">/{w.slug}</span></td>
                    <td className="px-3 py-2 text-muted">{w.email || '—'}</td>
                    <td className="px-3 py-2">{tier ? (PAKIET_L[tier] || tier) : <span className="text-muted">—</span>}</td>
                    <td className="px-3 py-2">
                      {puls ? (
                        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_KOLOR[puls.status] || 'bg-white/10 text-muted'}`}>
                          {puls.status}{puls.data_do ? ` · do ${puls.data_do}` : ''}
                        </span>
                      ) : <span className="text-xs text-muted">brak pulsu</span>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted">{puls ? puls.liczba_uzytkownikow : '—'}</td>
                    <td className="px-3 py-2 text-muted">{(w.utworzono_at || '').slice(0, 10) || '—'}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`inline-block h-2.5 w-2.5 rounded-full ${w.dziala ? 'bg-success' : 'bg-danger'}`}
                            title={w.dziala ? 'działa' : 'nie odpowiada'} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <a href={w.url} target="_blank" rel="noreferrer"
                         className="inline-flex items-center gap-1 text-xs font-semibold text-mint">
                        Wejdź <Icon name="chevronDown" className="h-3.5 w-3.5 -rotate-90" />
                      </a>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
