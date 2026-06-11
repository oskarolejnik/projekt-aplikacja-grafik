import { useEffect, useState, useCallback, useMemo } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { ddmmyyyy, NAZWY_DNI } from '../../lib/format'

// Podgląd rozliczeń kelnerów (admin). Liczą się WYŁĄCZNIE kwoty ZADEKLAROWANE przez kelnera:
//   • Gotówka (G) = zadeklarowana forma GOTÓWKA,
//   • Karta (T)   = zadeklarowana forma KARTA,
//   • FV          = faktury KARTA_FV + GOTÓWKA_FV — brane z systemu, bo kelner deklaruje tam 0
//                   (faktury nie idą przez kasę). PRZELEW_FV pomijamy.
// To, co naliczył system (sprzedaż), oraz formy niezadeklarowane (REPREZENTACJA, PRZELEW, ONLINE…)
// NIE są pokazywane. Układ jak w zeszycie: kelner → G / T / FV + SUMA. Pełne rozliczenie dnia
// (terminale, kasy, L, zadatek, KP/KW) dojdzie w Etapie D jako formularz.
const iso = (d) => d.toISOString().slice(0, 10)
const zl = (n) => (n || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'

export default function RozliczeniaPodglad() {
  const { toast } = useToast()
  const [od, setOd] = useState(iso(new Date(Date.now() - 7 * 86400000)))
  const [doDnia, setDoDnia] = useState(iso(new Date()))
  const [pozycje, setPozycje] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setPozycje((await api(`/gastro/rozliczenia?start=${od}&end=${doDnia}`)).pozycje || [])
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [od, doDnia, toast])

  useEffect(() => { load() }, [load])

  // Dzień → kelnerzy (jeden wiersz na rozliczenie) z kolumnami G / T / FV + suma dzienna.
  const dni = useMemo(() => {
    const byRoz = {}
    pozycje.forEach((p) => {
      const r = (byRoz[p.rozliczenie_id] ||= {
        id: p.rozliczenie_id, kelner: p.pracownik || p.imie_nazwisko,
        brakKonta: !p.pracownik, data: p.data, zamkniete: p.zamkniete, g: 0, t: 0, fv: 0,
      })
      if (p.forma === 'GOTÓWKA') r.g += p.deklarowane               // tylko ZADEKLAROWANE
      else if (p.forma === 'KARTA') r.t += p.deklarowane
      else if (p.forma === 'KARTA_FV' || p.forma === 'GOTÓWKA_FV') r.fv += p.sprzedaz  // FV z systemu
    })
    const byDay = {}
    Object.values(byRoz).forEach((r) => { (byDay[r.data] ||= []).push(r) })
    return Object.keys(byDay).sort().reverse().map((d) => {
      const kelnerzy = byDay[d].sort((a, b) => (a.kelner || '').localeCompare(b.kelner || ''))
      // Suma TYLKO z rozliczeń zamkniętych (otwarte jeszcze nic nie zadeklarowały).
      const suma = kelnerzy.reduce(
        (s, k) => (k.zamkniete ? { g: s.g + k.g, t: s.t + k.t, fv: s.fv + k.fv } : s),
        { g: 0, t: 0, fv: 0 },
      )
      return { data: d, kelnerzy, suma }
    })
  }, [pozycje])

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader
        title="Rozliczenia kelnerów — podgląd"
        subtitle="Wyłącznie kwoty zadeklarowane przez kelnerów (gotówka, karta) + faktury. To, co naliczył system, pomijamy. Pełne rozliczenie dnia (terminale, kasy, zadatek…) dojdzie w kolejnym etapie."
      />

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Od</span>
          <input type="date" value={od} onChange={(e) => setOd(e.target.value)} className="field" />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Do</span>
          <input type="date" value={doDnia} onChange={(e) => setDoDnia(e.target.value)} className="field" />
        </label>
      </div>

      <p className="mb-4 text-[11px] leading-snug text-muted/80">
        <b>Gotówka / Karta</b> = kwoty <b>zadeklarowane</b> przez kelnera przy rozliczeniu w POS.
        <span className="font-bold text-mint"> FV</span> = faktury (KARTA_FV + GOTÓWKA_FV). Reprezentacja, przelewy i ONLINE pomijamy.
      </p>

      {loading ? (
        <div className="grid place-items-center py-12"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : dni.length === 0 ? (
        <div className="rounded-xl border border-line bg-white/[0.02] p-8 text-center text-sm text-muted">
          Brak rozliczeń w tym zakresie. (Jeśli agent dopiero ruszył — dane pojawią się po rozliczeniu kelnera w POS.)
        </div>
      ) : (
        <div className="space-y-6">
          {dni.map(({ data, kelnerzy, suma }) => (
            <div key={data}>
              <div className="mb-2 flex items-baseline gap-2">
                <span className="font-semibold capitalize text-ink">{NAZWY_DNI[new Date(data).getDay()]}</span>
                <span className="text-xs text-muted">{ddmmyyyy(data)}</span>
              </div>
              <div className="overflow-x-auto rounded-xl border border-line">
                <table className="w-full min-w-[460px] text-sm">
                  <thead>
                    <tr className="bg-surface-2 text-[11px] uppercase tracking-wide text-muted">
                      <th className="px-3 py-2 text-left font-bold">Kelner</th>
                      <th className="px-3 py-2 text-right font-bold">Gotówka</th>
                      <th className="px-3 py-2 text-right font-bold">Karta</th>
                      <th className="px-3 py-2 text-right font-bold">FV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kelnerzy.map((k) => (
                      <tr key={k.id} className={`border-t border-line/60 ${k.zamkniete ? '' : 'opacity-60'}`}>
                        <td className="px-3 py-2 font-semibold text-ink">
                          {k.kelner}
                          {k.brakKonta && <span title="Brak dopasowanego konta w aplikacji" className="ml-1.5 text-xs font-normal text-blush">(bez konta)</span>}
                          {!k.zamkniete && <span className="ml-1.5 text-xs font-normal text-muted">· otwarte</span>}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-ink">{k.zamkniete ? zl(k.g) : '—'}</td>
                        <td className="px-3 py-2 text-right font-mono text-ink">{k.zamkniete ? zl(k.t) : '—'}</td>
                        <td className="px-3 py-2 text-right font-mono text-mint">{k.zamkniete && k.fv > 0 ? zl(k.fv) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-line bg-surface-2 font-bold">
                      <td className="px-3 py-2 text-left text-ink">SUMA (zadeklarowane)</td>
                      <td className="px-3 py-2 text-right font-mono text-ink">{zl(suma.g)}</td>
                      <td className="px-3 py-2 text-right font-mono text-ink">{zl(suma.t)}</td>
                      <td className="px-3 py-2 text-right font-mono text-mint">{zl(suma.fv)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
