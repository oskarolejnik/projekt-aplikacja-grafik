import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Ustawienia lokalu (admin): marka + moduły + parametry imprez + subskrypcja + status integracji.
// Backend: GET/PUT /api/lokal/config, GET /api/integracje/status, GET/PUT /api/subskrypcja.
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
  const [sub, setSub] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [c, i, s] = await Promise.all([api('/lokal/config'), api('/integracje/status'), api('/subskrypcja')])
      setCfg(c); setInteg(i.integracje || []); setSub(s)
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  const set = (k, v) => setCfg((s) => ({ ...s, [k]: v }))
  const setS = (k, v) => setSub((s) => ({ ...s, [k]: v }))

  const zapiszSub = async () => {
    setBusy(true)
    try {
      const r = await api('/subskrypcja', 'PUT', { status: sub.status, tier: sub.tier, data_do: sub.data_do || null })
      setSub(r); toast('Zapisano subskrypcję.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const zapisz = async () => {
    setBusy(true)
    try {
      await api('/lokal/config', 'PUT', {
        nazwa_lokalu: cfg.nazwa_lokalu, logo_url: cfg.logo_url || null, kolor_primary: cfg.kolor_primary || null,
        poczatek_tygodnia: Number(cfg.poczatek_tygodnia),
        modul_rezerwacje: cfg.modul_rezerwacje, modul_imprezy: cfg.modul_imprezy,
        modul_rozliczenia: cfg.modul_rozliczenia, modul_pos: cfg.modul_pos, modul_sprzatanie: cfg.modul_sprzatanie,
        rezerwacje_online: cfg.rezerwacje_online, rezerwacje_auto_potwierdzenie: cfg.rezerwacje_auto_potwierdzenie,
        impreza_osoby_na_obsluge: Number(cfg.impreza_osoby_na_obsluge),
        impreza_wyprzedzenie_min: Number(cfg.impreza_wyprzedzenie_min),
        impreza_najwczesniej: cfg.impreza_najwczesniej, impreza_sale_min2: cfg.impreza_sale_min2,
        obsada_rachunki_na_osobe: Number(cfg.obsada_rachunki_na_osobe),
        obsada_min: Number(cfg.obsada_min),
        praca_min_odpoczynek_h: Number(cfg.praca_min_odpoczynek_h),
        praca_max_dni_tydzien: Number(cfg.praca_max_dni_tydzien),
        praca_max_dni_miesiac: Number(cfg.praca_max_dni_miesiac),
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
        <SectionHeader title="Parametry obsady imprez" subtitle="Reguły automatycznego przeliczania obsady imprez na wymagania grafiku (moduł imprez)." />
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-muted">Gości na 1 pracownika obsługi
            <input type="number" min="1" value={cfg.impreza_osoby_na_obsluge ?? 15} onChange={(e) => set('impreza_osoby_na_obsluge', e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Start obsługi przed imprezą (min)
            <input type="number" min="0" value={cfg.impreza_wyprzedzenie_min ?? 120} onChange={(e) => set('impreza_wyprzedzenie_min', e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Najwcześniejsza godzina startu
            <input value={cfg.impreza_najwczesniej ?? '10:00'} onChange={(e) => set('impreza_najwczesniej', e.target.value)} placeholder="10:00" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Sale z minimum 2 obsady (po przecinku)
            <input value={cfg.impreza_sale_min2 ?? ''} onChange={(e) => set('impreza_sale_min2', e.target.value)} placeholder="R2Piw,R2G" className={fld} /></label>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Prognoza obsady" subtitle="Przeliczanie prognozowanego ruchu na sugerowaną liczbę osób na zmianę (zakładka „Prognoza obsady”)." />
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-muted">Rachunków na 1 osobę obsługi
            <input type="number" min="1" value={cfg.obsada_rachunki_na_osobe ?? 20} onChange={(e) => set('obsada_rachunki_na_osobe', e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Minimalna obsada na zmianę
            <input type="number" min="1" value={cfg.obsada_min ?? 1} onChange={(e) => set('obsada_min', e.target.value)} className={fld} /></label>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Strażnik prawa pracy" subtitle="Limity przy ręcznym przydziale zmian (Kodeks pracy). Wpisz 0, aby wyłączyć dany limit." />
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="text-xs font-semibold text-muted">Min. odpoczynek między zmianami (h)
            <input type="number" min="0" value={cfg.praca_min_odpoczynek_h ?? 11} onChange={(e) => set('praca_min_odpoczynek_h', e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Maks. dni pracy w tygodniu
            <input type="number" min="0" value={cfg.praca_max_dni_tydzien ?? 6} onChange={(e) => set('praca_max_dni_tydzien', e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Maks. dni pracy w miesiącu
            <input type="number" min="0" value={cfg.praca_max_dni_miesiac ?? 22} onChange={(e) => set('praca_max_dni_miesiac', e.target.value)} className={fld} /></label>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Rezerwacje online" subtitle="Publiczny widget — goście rezerwują bez logowania (wymaga modułu rezerwacji + godzin otwarcia + stolików)." />
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between rounded-xl border border-line bg-surface-2 px-4 py-3">
            <span className="text-sm text-ink">Włącz rezerwacje online</span>
            <Toggle on={!!cfg.rezerwacje_online} onChange={(v) => set('rezerwacje_online', v)} />
          </div>
          <div className="flex items-center justify-between rounded-xl border border-line bg-surface-2 px-4 py-3">
            <span className="text-sm text-ink">Automatyczne potwierdzanie (bez akceptacji admina)</span>
            <Toggle on={!!cfg.rezerwacje_auto_potwierdzenie} onChange={(v) => set('rezerwacje_auto_potwierdzenie', v)} />
          </div>
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

      {sub && (
        <Card className="p-6 sm:p-8">
          <SectionHeader title="Subskrypcja / licencja" subtitle="Status instancji. Nieaktywna = tryb tylko do odczytu (zapisy zablokowane)." />
          <div className="mt-4">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${sub.aktywna ? 'bg-mint/15 text-mint' : 'bg-danger/15 text-danger'}`}>
              {sub.aktywna ? 'Aktywna — zapisy dozwolone' : 'Nieaktywna — tryb tylko do odczytu'}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="text-xs font-semibold text-muted">Status
              <select value={sub.status} onChange={(e) => setS('status', e.target.value)} className={fld}>
                {['aktywna', 'trial', 'wygasla', 'zawieszona'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select></label>
            <label className="text-xs font-semibold text-muted">Plan (tier)
              <select value={sub.tier} onChange={(e) => setS('tier', e.target.value)} className={fld}>
                {['free', 'basic', 'pro', 'premium', 'enterprise'].map((t) => <option key={t} value={t}>{t}</option>)}
              </select></label>
            <label className="text-xs font-semibold text-muted">Ważna do (puste = bezterminowo)
              <input type="date" value={sub.data_do || ''} onChange={(e) => setS('data_do', e.target.value || null)} className={fld} /></label>
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={zapiszSub} disabled={busy}><Icon name="check" className="h-4 w-4" /> Zapisz subskrypcję</Button>
          </div>
        </Card>
      )}

      <div className="flex justify-end">
        <Button onClick={zapisz} disabled={busy}><Icon name="check" className="h-4 w-4" /> Zapisz ustawienia</Button>
      </div>
    </div>
  )
}
