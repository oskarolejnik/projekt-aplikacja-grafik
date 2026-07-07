import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Analityka rezerwacji — agregaty operacyjne (covery, no-show, mix kanałów, lead time, szczyty).
// Backend: /api/analityka/rezerwacje?start&end. Moduł za flagą modul_rezerwacje (Pro+).

const iso = (d) => d.toISOString().slice(0, 10)
const fld = 'rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none focus:border-mint'
const KANAL_L = { online: 'Online', reczna: 'Ręczna', google: 'Google', ical: 'iCal', walk_in: 'Walk-in' }

export default function AnalitykaRezerwacji() {
  const { toast } = useToast()
  const dzis = new Date()
  const [start, setStart] = useState(iso(new Date(dzis.getTime() - 29 * 864e5)))
  const [end, setEnd] = useState(iso(dzis))
  const [a, setA] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try { setA(await api(`/analityka/rezerwacje?start=${start}&end=${end}`)) }
    catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [start, end, toast])
  useEffect(() => { load() }, [load])

  const s = a?.statusy || {}
  const maxDzien = Math.max(1, ...((a?.covery?.wg_dnia || []).map((d) => d.covery)))
  const maxTyg = Math.max(1, ...((a?.szczyty?.wg_dnia_tygodnia || []).map((d) => d.covery)))
  const maxGodz = Math.max(1, ...((a?.szczyty?.wg_godziny || []).map((d) => d.covery)))
  const maxGrupa = Math.max(1, ...((a?.wielkosc_grup || []).map((g) => g.liczba)))

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Analityka rezerwacji" subtitle="Covery, no-show, mix kanałów, wyprzedzenie i szczyty ruchu — z danych rezerwacji." />
        <div className="flex items-center gap-2 text-sm">
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={fld} />
          <span className="text-muted">—</span>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={fld} />
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : !a ? null : (
        <div className="space-y-6">
          {/* Kluczowe metryki */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="Covery" value={a.covery.suma} sub={`śr. ${a.covery.srednia_dzienna}/dzień`} akcent />
            <Stat label="No-show" value={`${s.no_show_proc}%`} sub={`${s.no_show} nieobecnych`} ton={s.no_show_proc >= 15 ? 'danger' : 'muted'} />
            <Stat label="Konwersja" value={`${s.konwersja_proc}%`} sub="przyszli / rozliczeni" ton="mint" />
            <Stat label="Wyprzedzenie" value={`${a.lead_time.mediana_dni} dni`} sub="mediana rezerwacji" />
            <Stat label="Odbyte" value={s.odbyla} sub={`${s.aktywne} aktywnych`} />
          </div>

          {/* Covery wg dnia */}
          <Sekcja tytul="Covery wg dnia">
            {a.covery.wg_dnia.length === 0 ? <Pusto /> : (
              <div className="space-y-1.5">
                {a.covery.wg_dnia.map((d) => (
                  <Bar key={d.data} etykieta={new Date(d.data).toLocaleDateString('pl-PL', { day: '2-digit', month: 'short' })}
                       wartosc={d.covery} max={maxDzien} suffix={`${d.covery} os. · ${d.rezerwacje} rez.`} />
                ))}
              </div>
            )}
          </Sekcja>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Mix kanałów */}
            <Sekcja tytul="Mix źródeł">
              {a.kanaly.length === 0 ? <Pusto /> : (
                <div className="space-y-1.5">
                  {a.kanaly.map((k) => (
                    <Bar key={k.kanal} etykieta={KANAL_L[k.kanal] || k.kanal} wartosc={k.proc} max={100} suffix={`${k.proc}% · ${k.liczba}`} />
                  ))}
                </div>
              )}
            </Sekcja>

            {/* Wielkość grup */}
            <Sekcja tytul="Wielkość grup">
              {a.wielkosc_grup.length === 0 ? <Pusto /> : (
                <div className="space-y-1.5">
                  {a.wielkosc_grup.map((g) => (
                    <Bar key={g.osoby} etykieta={`${g.etykieta} os.`} wartosc={g.liczba} max={maxGrupa} suffix={`${g.liczba}`} />
                  ))}
                </div>
              )}
            </Sekcja>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Szczyty wg dnia tygodnia */}
            <Sekcja tytul="Szczyty — dzień tygodnia">
              <div className="flex items-end gap-2 pt-2">
                {a.szczyty.wg_dnia_tygodnia.map((d) => (
                  <Kolumna key={d.dzien} etykieta={d.dzien} wartosc={d.covery} max={maxTyg} />
                ))}
              </div>
            </Sekcja>

            {/* Szczyty wg godziny */}
            <Sekcja tytul="Szczyty — godzina">
              {a.szczyty.wg_godziny.length === 0 ? <Pusto /> : (
                <div className="flex items-end gap-1.5 pt-2">
                  {a.szczyty.wg_godziny.map((g) => (
                    <Kolumna key={g.godz} etykieta={g.godz.slice(0, 2)} wartosc={g.covery} max={maxGodz} />
                  ))}
                </div>
              )}
            </Sekcja>
          </div>
        </div>
      )}
    </Card>
  )
}

function Stat({ label, value, sub, akcent, ton }) {
  const kolor = ton === 'danger' ? 'text-danger' : ton === 'mint' ? 'text-mint' : 'text-ink'
  return (
    <div className={`rounded-xl border p-3.5 ${akcent ? 'border-mint/30 bg-mint/[0.06]' : 'border-line bg-surface-2'}`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 font-display text-2xl font-bold tabular-nums ${kolor}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-muted">{sub}</div>}
    </div>
  )
}

function Sekcja({ tytul, children }) {
  return (
    <div>
      <h3 className="mb-2 font-display text-sm font-bold text-ink">{tytul}</h3>
      {children}
    </div>
  )
}

function Bar({ etykieta, wartosc, max, suffix }) {
  const pct = Math.round((wartosc / max) * 100)
  return (
    <div className="flex items-center gap-3">
      <div className="w-24 shrink-0 truncate text-xs text-muted">{etykieta}</div>
      <div className="h-5 flex-1 overflow-hidden rounded-md bg-white/[0.04]">
        <div className="h-full rounded-md bg-mint/60" style={{ width: `${Math.max(pct, wartosc > 0 ? 4 : 0)}%` }} />
      </div>
      <div className="w-28 shrink-0 text-right text-xs tabular-nums text-muted">{suffix}</div>
    </div>
  )
}

function Kolumna({ etykieta, wartosc, max }) {
  const pct = Math.round((wartosc / max) * 100)
  return (
    <div className="flex flex-1 flex-col items-center gap-1">
      <div className="text-[10px] tabular-nums text-muted">{wartosc || ''}</div>
      <div className="flex h-24 w-full items-end">
        <div className="w-full rounded-t bg-mint/50" style={{ height: `${Math.max(pct, wartosc > 0 ? 6 : 0)}%` }} />
      </div>
      <div className="text-[10px] text-muted">{etykieta}</div>
    </div>
  )
}

function Pusto() {
  return <div className="rounded-xl border border-dashed border-line px-3 py-6 text-center text-xs text-muted">Brak danych w tym okresie.</div>
}
