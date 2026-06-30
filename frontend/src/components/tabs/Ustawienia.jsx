import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Ustawienia lokalu (admin): marka (white-label) + przełączniki modułów + status integracji.
// Backend: GET/PUT /api/lokal/config, GET /api/integracje/status.
const DNI = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
const MODULY = [
  ['modul_rezerwacje', 'Rezerwacje stolików'],
  ['modul_imprezy', 'Imprezy / wesela'],
  ['modul_rozliczenia', 'Rozliczenia kasowe'],
  ['modul_pos', 'Integracja POS / RCP'],
  ['modul_sprzatanie', 'Grafik sprzątania'],
]
const fld = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-mint'

function Toggle({ on, onChange }) {
  return (
    <button type="button" onClick={() => onChange(!on)} role="switch" aria-checked={on}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? 'bg-accent-gradient' : 'bg-white/10'}`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-bg shadow transition-all ${on ? 'left-[1.375rem]' : 'left-0.5'}`} />
    </button>
  )
}

export default function Ustawienia() {
  const { toast } = useToast()
  const [cfg, setCfg] = useState(null)
  const [integ, setInteg] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [c, i] = await Promise.all([api('/lokal/config'), api('/integracje/status')])
      setCfg(c); setInteg(i.integracje || [])
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  const set = (k, v) => setCfg((s) => ({ ...s, [k]: v }))

  const zapisz = async () => {
    setBusy(true)
    try {
      await api('/lokal/config', 'PUT', {
        nazwa_lokalu: cfg.nazwa_lokalu, logo_url: cfg.logo_url || null, kolor_primary: cfg.kolor_primary || null,
        poczatek_tygodnia: Number(cfg.poczatek_tygodnia),
        modul_rezerwacje: cfg.modul_rezerwacje, modul_imprezy: cfg.modul_imprezy,
        modul_rozliczenia: cfg.modul_rozliczenia, modul_pos: cfg.modul_pos, modul_sprzatanie: cfg.modul_sprzatanie,
      })
      toast('Zapisano. Odśwież stronę, by zobaczyć zmiany w marce i nawigacji.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  if (loading || !cfg) {
    return <Card className="p-8"><div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div></Card>
  }

  return (
    <div className="space-y-5">
      <Card className="p-6 sm:p-8">
        <SectionHeader title="Marka (white-label)" subtitle="Nazwa, logo i kolor widoczne w całej aplikacji." />
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-muted">Nazwa lokalu
            <input value={cfg.nazwa_lokalu || ''} onChange={(e) => set('nazwa_lokalu', e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Kolor (hex)
            <input value={cfg.kolor_primary || ''} onChange={(e) => set('kolor_primary', e.target.value)} placeholder="#2bb673" className={fld} /></label>
          <label className="text-xs font-semibold text-muted sm:col-span-2">Logo (URL)
            <input value={cfg.logo_url || ''} onChange={(e) => set('logo_url', e.target.value)} placeholder="https://…/logo.png" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Początek tygodnia grafiku
            <select value={cfg.poczatek_tygodnia} onChange={(e) => set('poczatek_tygodnia', e.target.value)} className={fld}>
              {DNI.map((d, i) => <option key={i} value={i}>{d}</option>)}
            </select></label>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Moduły" subtitle="Włącz tylko funkcje, których używasz. Wyłączone znikają z nawigacji." />
        <div className="mt-4 space-y-2">
          {MODULY.map(([k, l]) => (
            <div key={k} className="flex items-center justify-between rounded-xl border border-line bg-surface-2 px-4 py-3">
              <span className="text-sm text-ink">{l}</span>
              <Toggle on={!!cfg[k]} onChange={(v) => set(k, v)} />
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Integracje" subtitle="Status połączeń — konfigurowane sekretami instancji (.env)." />
        <div className="mt-4 space-y-2">
          {integ.map((i) => (
            <div key={i.klucz} className="flex items-center justify-between rounded-xl border border-line bg-surface-2 px-4 py-3">
              <span className="text-sm text-ink">{i.nazwa}</span>
              <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${i.skonfigurowane ? 'bg-mint/15 text-mint' : 'bg-white/10 text-muted'}`}>
                {i.skonfigurowane ? 'Aktywna' : 'Nieskonfigurowana'}
              </span>
            </div>
          ))}
        </div>
      </Card>

      <div className="flex justify-end">
        <Button onClick={zapisz} disabled={busy}><Icon name="check" className="h-4 w-4" /> Zapisz ustawienia</Button>
      </div>
    </div>
  )
}
