import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Pulpit właściciela — KPI lokalu w okresie. Czysta agregacja z /api/pulpit (zero zapisu).
const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const dzisISO = () => new Date().toISOString().slice(0, 10)
const isoMinus = (days) => { const d = new Date(); d.setDate(d.getDate() - days); return d.toISOString().slice(0, 10) }

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

export default function Pulpit() {
  const { toast } = useToast()
  const [start, setStart] = useState(isoMinus(29))
  const [end, setEnd] = useState(dzisISO())
  const [p, setP] = useState(null)
  const [alerty, setAlerty] = useState(null)
  const [obsada, setObsada] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [pul, al, ob] = await Promise.all([
        api(`/pulpit?start=${start}&end=${end}`),
        api(`/alerty-kasowe?start=${start}&end=${end}`),
        api('/alerty-obsady?dni=14'),
      ])
      setP(pul); setAlerty(al); setObsada(ob)
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [start, end, toast])
  useEffect(() => { load() }, [load])

  const maxPrzychod = p ? Math.max(1, ...p.przychod.dzienny.map((d) => d.przychod)) : 1

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Pulpit właściciela" subtitle="Kluczowe wskaźniki lokalu w wybranym okresie." />
        <div className="flex items-center gap-2 text-sm">
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-ink outline-none focus:border-mint" />
          <span className="text-muted">—</span>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-lg border border-line bg-surface px-3 py-1.5 text-ink outline-none focus:border-mint" />
        </div>
      </div>

      {loading || !p ? (
        <div className="grid place-items-center py-20"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Kpi label="Przychód" value={zl(p.przychod.razem)} sub={`śr. ${zl(p.przychod.srednia_dzienna)}/dzień`} icon="download" accent="text-mint" />
            <Kpi label="Rozchód" value={zl(p.rozchod.razem)} icon="upload" />
            <Kpi label="Saldo kasy" value={zl(p.saldo_kasy)} sub="stan gotówki narastająco" icon="clipboard" />
            <Kpi label="Ruch (rachunki)" value={p.ruch.rachunki} sub={`śr. ${p.ruch.srednia_dzienna}/dzień`} icon="pin" />
            <Kpi label="Rezerwacje" value={p.rezerwacje.razem} sub={`${p.rezerwacje.goscie} gości`} icon="calendar" />
            <Kpi label={`Koszt pracy (${String(p.koszt_pracy_miesiac.miesiac).padStart(2, '0')}.${p.koszt_pracy_miesiac.rok})`} value={zl(p.koszt_pracy_miesiac.kwota)} icon="users" />
            <Kpi label="Alerty kasowe" value={p.alerty_kasowe.dni_z_anomalia}
                 sub={p.alerty_kasowe.suma_braki < 0 ? `braki ${zl(p.alerty_kasowe.suma_braki)}` : 'brak braków'}
                 icon="warning" accent={p.alerty_kasowe.dni_z_anomalia > 0 ? 'text-danger' : 'text-ink'} />
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[['Gotówka', 'gotowka'], ['Karta', 'karta'], ['Przelew', 'przelew'], ['Impreza', 'impreza']].map(([l, k]) => (
              <div key={k} className="rounded-xl border border-line bg-surface px-4 py-3">
                <div className="text-xs text-muted">{l}</div>
                <div className="font-display font-bold text-ink">{zl(p.przychod[k])}</div>
              </div>
            ))}
          </div>

          {p.przychod.dzienny.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Przychód dzienny</div>
              <div className="flex h-40 items-end gap-1 overflow-x-auto rounded-xl border border-line bg-surface p-3">
                {p.przychod.dzienny.map((d) => (
                  <div key={d.data} className="flex min-w-[8px] flex-1 flex-col items-center" title={`${d.data}: ${zl(d.przychod)}`}>
                    <div className="w-full rounded-t bg-accent-gradient" style={{ height: `${Math.round((d.przychod / maxPrzychod) * 100)}%`, minHeight: d.przychod > 0 ? '4px' : '0' }} />
                  </div>
                ))}
              </div>
            </div>
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

          {obsada?.alerty?.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
                <Icon name="warning" className="h-4 w-4 text-lemon" /> Niedobór obsady (najbliższe {obsada.dni} dni) — brakuje {obsada.razem_brakuje} os.
              </div>
              <div className="space-y-2">
                {obsada.alerty.map((a, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 rounded-xl border border-lemon/30 bg-lemon/[0.05] px-4 py-2.5 text-sm">
                    <span className="text-ink"><b>{a.data}</b> · {a.stanowisko}</span>
                    <span className="text-muted">obsadzone {a.obsadzone}/{a.wymagane} · <b className="text-lemon">brakuje {a.brakuje}</b></span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {alerty && alerty.alerty.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Anomalie kasowe (różnice w rozliczeniu)</div>
              <div className="space-y-2">
                {alerty.alerty.map((a) => (
                  <div key={a.data} className="rounded-xl border border-danger/30 bg-danger/5 px-4 py-3">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-ink">{a.data}</span>
                      <span className="text-xs text-muted">{a.status}</span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs">
                      {a.problemy.map((pr, i) => (
                        <span key={i} className={`rounded-full px-2 py-0.5 ${pr.roznica < 0 ? 'bg-danger/15 text-danger' : 'bg-lemon/15 text-lemon'}`}>
                          {pr.typ === 'karty' ? 'Karty' : 'Kasa'}: {zl(pr.roznica)}{pr.etykieta ? ` · ${pr.etykieta}` : ''}
                        </span>
                      ))}
                    </div>
                  </div>
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
    </Card>
  )
}
