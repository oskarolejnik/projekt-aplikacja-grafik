import { useEffect, useState, useCallback } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Hint } from '../ui/Hint'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api, pobierzPlik } from '../../lib/api'
import { useToast } from '../ui/Toast'
import { TYPY, TYP_PO_ID, znormalizujModuly } from '../../pages/onboarding/typy'

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
const ETYKIETA_PLANU = { free: 'Darmowy', basic: 'Basic', pro: 'Pro', premium: 'Premium', enterprise: 'Enterprise' }
const fld = 'w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-mint'

function Toggle({ on, onChange }) {
  return (
    <button type="button" onClick={() => onChange(!on)} role="switch" aria-checked={on}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? 'bg-mint' : 'bg-white/10'}`}>
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

  // Etykiety kas/terminali edytowane jako tekst „po przecinku" (puste = wolny wpis w Rozliczeniu dnia).
  const [kasyText, setKasyText] = useState('')
  const [terminaleText, setTerminaleText] = useState('')
  // Struktura lokalu: listy po przecinku + mapa „kod=Sala" (puste = wartości domyślne/legacy).
  const [saleText, setSaleText] = useState('')
  const [saleCodzText, setSaleCodzText] = useState('')
  const [salaNiedziela, setSalaNiedziela] = useState('')
  const [mapaSalText, setMapaSalText] = useState('')
  const [zeszytKolText, setZeszytKolText] = useState('')
  const [excelMapa, setExcelMapa] = useState({ godzina: 'J1', osoby: 'H8', sala: 'J2' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [c, i, s] = await Promise.all([api('/lokal/config'), api('/integracje/status'), api('/subskrypcja')])
      setCfg(c); setInteg(i.integracje || []); setSub(s)
      setKasyText((c.rozliczenia_nazwy_kas || []).join(', '))
      setTerminaleText((c.rozliczenia_nazwy_terminali || []).join(', '))
      setSaleText((c.sale || []).join(', '))
      setSaleCodzText((c.sprzatanie_sale_codziennie || []).join(', '))
      setSalaNiedziela(c.sprzatanie_sala_niedziela ?? 'Zielona')   // NULL = legacy „Zielona"
      setMapaSalText(Object.entries(c.imprezy_mapa_sal || {}).map(([k, v]) => `${k}=${v}`).join(', '))
      setZeszytKolText((c.zeszyt_kolumny || []).join(', '))
      setExcelMapa({ godzina: 'J1', osoby: 'H8', sala: 'J2', ...(c.imprezy_excel_mapa || {}) })
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  const set = (k, v) => setCfg((s) => ({ ...s, [k]: v }))
  const setS = (k, v) => setSub((s) => ({ ...s, [k]: v }))

  // Menu imprez (portal Pary Młodej): katalog ofert wybieralnych przez klienta w portalu.
  const [oferty, setOferty] = useState([])
  const [nowaOferta, setNowaOferta] = useState({ nazwa: '', cena_od_osoby: '', opis: '' })
  useEffect(() => { api('/oferty-menu').then(setOferty).catch(() => {}) }, [])
  const odswiezOferty = async () => setOferty(await api('/oferty-menu'))
  const dodajOferte = async () => {
    if (!nowaOferta.nazwa.trim()) { toast('Podaj nazwę oferty.', 'error'); return }
    try {
      await api('/oferty-menu', 'POST', {
        nazwa: nowaOferta.nazwa.trim(), opis: nowaOferta.opis.trim(),
        cena_od_osoby: parseFloat(nowaOferta.cena_od_osoby) || 0, aktywna: true,
      })
      setNowaOferta({ nazwa: '', cena_od_osoby: '', opis: '' })
      await odswiezOferty(); toast('Dodano ofertę menu.', 'success')
    } catch (e) { toast(e.message, 'error') }
  }
  const przelaczOferte = async (o) => {
    try { await api(`/oferty-menu/${o.id}`, 'PUT', { ...o, aktywna: !o.aktywna }); await odswiezOferty() }
    catch (e) { toast(e.message, 'error') }
  }
  const usunOferte = async (o) => {
    try { await api(`/oferty-menu/${o.id}`, 'DELETE'); await odswiezOferty(); toast('Usunięto ofertę.', 'success') }
    catch (e) { toast(e.message, 'error') }
  }

  const zapiszSub = async () => {
    setBusy(true)
    try {
      const r = await api('/subskrypcja', 'PUT', { status: sub.status, tier: sub.tier, data_do: sub.data_do || null })
      setSub(r); toast('Zapisano subskrypcję.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  // Zmiana planu z dopłatą (proration) + odnowienie abonamentu (sandbox: link do opłacenia).
  const [nowyTier, setNowyTier] = useState('')
  const [podglad, setPodglad] = useState(null)     // wynik proraty
  const [platnoscSub, setPlatnoscSub] = useState(null)  // {external_id, brutto, link}
  const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'

  const podgladUpgrade = async (tier) => {
    setNowyTier(tier); setPodglad(null)
    if (!tier || tier === sub.tier) return
    try { setPodglad(await api(`/subskrypcja/upgrade/podglad?tier=${tier}`)) }
    catch (e) { toast(e.message, 'error') }
  }
  const wykonajUpgrade = async () => {
    setBusy(true)
    try {
      const r = await api('/subskrypcja/upgrade', 'POST', { tier: nowyTier })
      setSub(r.subskrypcja); setPlatnoscSub(r.platnosc); setPodglad(null); setNowyTier('')
      toast(r.platnosc ? 'Plan zmieniony — opłać dopłatę.' : 'Plan zmieniony.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const odnow = async () => {
    setBusy(true)
    try { setPlatnoscSub(await api('/subskrypcja/odnow', 'POST')); toast('Utworzono płatność za kolejny okres.', 'success') }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const [faktury, setFaktury] = useState(null)
  const odswiezFaktury = useCallback(async () => {
    try { setFaktury(await api('/faktury')) } catch { /* endpoint tylko na instancji z billingiem */ }
  }, [])
  useEffect(() => { odswiezFaktury() }, [odswiezFaktury])

  const oplacSandbox = async () => {
    setBusy(true)
    try {
      const r = await api(`/subskrypcja/platnosc/${platnoscSub.external_id}/oplac`, 'POST')
      setSub(r); setPlatnoscSub(null); await odswiezFaktury()
      toast('Zaksięgowano płatność (sandbox) — wystawiono fakturę.', 'success')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const pobierzFakture = async (f) => {
    try { await pobierzPlik(`/faktury/${f.id}/xml`, `${f.numer.replace(/\//g, '_')}.xml`) }
    catch (e) { toast(e.message, 'error') }
  }

  const zapisz = async () => {
    setBusy(true)
    try {
      await api('/lokal/config', 'PUT', {
        nazwa_lokalu: cfg.nazwa_lokalu, logo_url: cfg.logo_url || null, kolor_primary: cfg.kolor_primary || null,
        typ_lokalu: cfg.typ_lokalu || null,
        poczatek_tygodnia: Number(cfg.poczatek_tygodnia),
        grafik_cykl: cfg.grafik_cykl || 'tydzien',
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
        impreza_osobne_rozliczenie: cfg.impreza_osobne_rozliczenie,
        rozliczenia_tryb_kelnera: cfg.rozliczenia_tryb_kelnera || 'indywidualnie',
        rozliczenia_nazwy_kas: kasyText.split(',').map((t) => t.trim()).filter(Boolean),
        rozliczenia_nazwy_terminali: terminaleText.split(',').map((t) => t.trim()).filter(Boolean),
        sale: saleText.split(',').map((t) => t.trim()).filter(Boolean),
        sprzatanie_sale_codziennie: saleCodzText.split(',').map((t) => t.trim()).filter(Boolean),
        sprzatanie_sala_niedziela: salaNiedziela.trim(),   // pusty = reguła wyłączona
        imprezy_mapa_sal: Object.fromEntries(mapaSalText.split(',')
          .map((p) => p.split('=').map((t) => t.trim()))
          .filter((p) => p.length === 2 && p[0] && p[1])),
        zeszyt_kolumny: zeszytKolText.split(',').map((t) => t.trim()).filter(Boolean),
        imprezy_excel_mapa: excelMapa,
        faktura_nip: cfg.faktura_nip || null, faktura_nazwa: cfg.faktura_nazwa || null,
        faktura_adres_l1: cfg.faktura_adres_l1 || null, faktura_adres_l2: cfg.faktura_adres_l2 || null,
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
          <label className="text-xs font-semibold text-muted">Cykl grafiku
            <select value={cfg.grafik_cykl || 'tydzien'} onChange={(e) => set('grafik_cykl', e.target.value)} className={fld}>
              <option value="tydzien">Tygodniowy</option>
              <option value="miesiac">Miesięczny (miesiąc kalendarzowy)</option>
            </select></label>
          <label className="text-xs font-semibold text-muted">Początek tygodnia grafiku
            <select value={cfg.poczatek_tygodnia} onChange={(e) => set('poczatek_tygodnia', e.target.value)}
                    disabled={cfg.grafik_cykl === 'miesiac'} className={`${fld} disabled:opacity-50`}>
              {DNI.map((d, i) => <option key={i} value={i}>{d}</option>)}
            </select></label>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Moduły" subtitle="Włącz tylko funkcje, których używasz. Moduły spoza Twojego planu są zablokowane — odblokujesz je podnosząc pakiet." />
        <div className="mt-4 space-y-2">
          {MODULY.map(([k, l]) => {
            const ok = !sub?.dostepne_moduly || sub.dostepne_moduly.includes(k)
            const plan = sub?.moduly_wg_planu?.[k]
            return (
              <div key={k} className={`flex items-center justify-between rounded-xl border px-4 py-3 ${ok ? 'border-line bg-surface-2' : 'border-line/60 bg-surface-2/40'}`}>
                <span className="flex items-center gap-2 text-sm text-ink">
                  {!ok && <Icon name="key" className="h-3.5 w-3.5 text-muted" />}
                  {l}
                  {!ok && plan && <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] font-semibold text-muted">{ETYKIETA_PLANU[plan]}+</span>}
                </span>
                {ok ? (
                  <Toggle on={!!cfg[k]} onChange={(v) => (k === 'modul_rezerwacje' && !v)
                    ? setCfg((s) => ({ ...s, modul_rezerwacje: false, rezerwacje_online: false }))
                    : set(k, v)} />
                ) : (
                  <button onClick={() => document.getElementById('sekcja-subskrypcja')?.scrollIntoView({ behavior: 'smooth' })}
                    className="text-xs font-semibold text-mint transition hover:brightness-110">Odblokuj →</button>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Typ lokalu" subtitle="Profil Twojej knajpy — z niego dobieramy sensowny zestaw modułów. „Zastosuj preset” ustawi przełączniki modułów wg wybranego typu (zapisz, by utrwalić) — możesz to zrobić ponownie w każdej chwili." />
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex-1 text-xs font-semibold text-muted">Typ
            <select value={cfg.typ_lokalu || ''} onChange={(e) => set('typ_lokalu', e.target.value || null)} className={fld}>
              <option value="">— nie wybrano —</option>
              {TYPY.map((t) => <option key={t.id} value={t.id}>{t.nazwa}</option>)}
            </select>
          </label>
          <Button variant="ghost" size="md" disabled={!cfg.typ_lokalu || !TYP_PO_ID[cfg.typ_lokalu]}
            onClick={() => setCfg((s) => ({ ...s, ...znormalizujModuly(TYP_PO_ID[s.typ_lokalu].moduly) }))}>
            <Icon name="refresh" className="h-4 w-4" /> Zastosuj preset modułów
          </Button>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Parametry obsady imprez" subtitle="Reguły automatycznego przeliczania obsady imprez na wymagania grafiku (moduł imprez). Komórki Excel dotyczą importu imprez z plików (moduł „Baza imprez”) — każdy lokal ma własny szablon." />
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
        <div className="mt-4 grid grid-cols-3 gap-3">
          <label className="text-xs font-semibold text-muted">Komórka Excel: godzina
            <input value={excelMapa.godzina} onChange={(e) => setExcelMapa((s) => ({ ...s, godzina: e.target.value.toUpperCase() }))} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Komórka Excel: liczba osób
            <input value={excelMapa.osoby} onChange={(e) => setExcelMapa((s) => ({ ...s, osoby: e.target.value.toUpperCase() }))} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Komórka Excel: sala
            <input value={excelMapa.sala} onChange={(e) => setExcelMapa((s) => ({ ...s, sala: e.target.value.toUpperCase() }))} className={fld} /></label>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Rozliczenie dnia" subtitle="Dopasuj kasę do swojego lokalu — nie każda knajpa rozlicza się jak dom weselny. Podane niżej etykiety kas/terminali pojawią się jako lista wyboru w Rozliczeniu dnia — liczba pozycji wynika z długości list." />
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between gap-4 rounded-xl border border-line bg-surface-2 px-4 py-3">
            <span className="flex items-center gap-1.5 text-sm text-ink">
              Imprezy rozliczane osobno
              <Hint>Włączone: rozliczenia imprez trafiają do zeszytu i pulpitu, a IMP pomniejsza kasy. Wyłączone: sprzedaż imprezowa siedzi w zwykłym obrocie sali (bez osobnych rozliczeń).</Hint>
            </span>
            <Toggle on={!!cfg.impreza_osobne_rozliczenie} onChange={(v) => set('impreza_osobne_rozliczenie', v)} />
          </div>
          <label className="block text-xs font-semibold text-muted">Sposób rozliczania obsługi
            <select value={cfg.rozliczenia_tryb_kelnera || 'indywidualnie'} onChange={(e) => set('rozliczenia_tryb_kelnera', e.target.value)} className={fld}>
              <option value="indywidualnie">Każdy kelner rozlicza się sam (wiersz per osoba)</option>
              <option value="pula">Wspólna pula sali (jedno zbiorcze rozliczenie zmiany)</option>
            </select>
          </label>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="text-xs font-semibold text-muted">Kasy — etykiety po przecinku (puste = wolny wpis)
              <input value={kasyText} onChange={(e) => setKasyText(e.target.value)} placeholder="np. Kasa główna, Kasa bar" className={fld} /></label>
            <label className="text-xs font-semibold text-muted">Terminale — etykiety po przecinku (puste = wolny wpis)
              <input value={terminaleText} onChange={(e) => setTerminaleText(e.target.value)} placeholder="np. Terminal 1, Terminal ogródek" className={fld} /></label>
          </div>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Struktura lokalu" subtitle="Sale i reguły sprzątania Twojego lokalu (puste pole = wartości domyślne). Kolejność sal = kolejność wyświetlania. Sale napędzają też grafik sprzątania i widok stołów; zmiana nazwy sali nie zmienia wpisów historycznych (zostają pod starą nazwą)." />
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-muted sm:col-span-2">Sale (po przecinku)
            <input value={saleText} onChange={(e) => setSaleText(e.target.value)} placeholder="np. Sala główna, Ogródek, Antresola" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Sprzątane codziennie (po przecinku)
            <input value={saleCodzText} onChange={(e) => setSaleCodzText(e.target.value)} placeholder="np. Sala główna" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Sala sprzątana w niedzielę (puste = bez reguły)
            <input value={salaNiedziela} onChange={(e) => setSalaNiedziela(e.target.value)} className={fld} /></label>
          <label className="text-xs font-semibold text-muted sm:col-span-2">Mapa sal z plików imprez (kod=Sala, po przecinku)
            <input value={mapaSalText} onChange={(e) => setMapaSalText(e.target.value)} placeholder="np. r2p=Zielona, r2piw=Lustrzana" className={fld} /></label>
          <label className="text-xs font-semibold text-muted sm:col-span-2">Kolumny rozchodu w zeszycie (po przecinku; puste = Towar, Koszty, Wypłaty, Inne)
            <input value={zeszytKolText} onChange={(e) => setZeszytKolText(e.target.value)} placeholder="np. towar, koszty, media, wypłaty" className={fld} /></label>
        </div>
      </Card>

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Menu imprez (portal klienta)" subtitle="Warianty menu, które para młoda / organizator wybiera w portalu imprezy. Nieaktywne znikają z portalu, wybory zostają." />
        <div className="space-y-2">
          {oferty.length === 0 && <p className="py-3 text-sm text-muted">Brak ofert — dodaj pierwszą, a pojawi się w portalu klienta.</p>}
          {oferty.map((o) => (
            <div key={o.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line bg-white/[0.02] px-4 py-2.5">
              <button onClick={() => przelaczOferte(o)}
                      className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold transition ${
                        o.aktywna ? 'bg-mint/15 text-mint' : 'bg-white/[0.06] text-muted hover:text-ink'}`}>
                {o.aktywna ? 'aktywna' : 'wyłączona'}
              </button>
              <div className="min-w-0 flex-1">
                <span className="text-sm font-semibold text-ink">{o.nazwa}</span>
                {o.opis && <span className="ml-2 text-xs text-muted">{o.opis}</span>}
              </div>
              <span className="text-sm tabular-nums text-ink">{(o.cena_od_osoby || 0).toLocaleString('pl-PL')} zł/os.</span>
              <button onClick={() => usunOferte(o)} className="text-muted transition hover:text-danger" aria-label="Usuń ofertę">✕</button>
            </div>
          ))}
          <div className="grid gap-2 pt-1 sm:grid-cols-[1fr_7rem_1fr_auto]">
            <input value={nowaOferta.nazwa} onChange={(e) => setNowaOferta((s) => ({ ...s, nazwa: e.target.value }))}
                   className={fld} placeholder="np. Menu Klasyczne" />
            <input type="number" value={nowaOferta.cena_od_osoby} onChange={(e) => setNowaOferta((s) => ({ ...s, cena_od_osoby: e.target.value }))}
                   className={fld} placeholder="zł/os." />
            <input value={nowaOferta.opis} onChange={(e) => setNowaOferta((s) => ({ ...s, opis: e.target.value }))}
                   className={fld} placeholder="opis (np. 3 dania + bufet)" />
            <Button variant="ghost" onClick={dodajOferte}>Dodaj</Button>
          </div>
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
            <span className="text-sm text-ink">Włącz rezerwacje online <span className="text-xs text-muted">(włączy też moduł rezerwacji)</span></span>
            <Toggle on={!!cfg.rezerwacje_online} onChange={(v) => setCfg((s) => ({ ...s, ...znormalizujModuly({ ...s, rezerwacje_online: v }) }))} />
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

      <div id="sekcja-subskrypcja" />
      {sub && (
        <Card className="p-6 sm:p-8">
          <SectionHeader title="Subskrypcja / licencja" subtitle="Twój pakiet, moduły, płatności i zmiana planu. Po grace instancja przechodzi w tryb tylko do odczytu." />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
              sub.stan === 'aktywna' ? 'bg-mint/15 text-mint' : sub.stan === 'grace' ? 'bg-lemon/15 text-lemon' : 'bg-danger/15 text-danger'}`}>
              {sub.stan === 'aktywna' ? 'Aktywna — zapisy dozwolone'
                : sub.stan === 'grace' ? `Po terminie — zapłać do ${sub.data_grace}, potem blokada`
                : 'Zablokowana — tryb tylko do odczytu'}
            </span>
            {sub.trial_dni != null && (
              <span className="rounded-full bg-mint/15 px-3 py-1 text-xs font-semibold text-mint">
                14 dni za darmo — {sub.trial_dni === 0 ? 'ostatni dzień' : `zostało ${sub.trial_dni} dni`}
              </span>
            )}
            <span className="text-sm text-muted">Pakiet <b className="text-ink">{ETYKIETA_PLANU[sub.tier] || sub.tier}</b> · {zl(sub.cena_brutto)}/mc brutto
              {sub.saldo_kredytu > 0 && <> · kredyt {zl(sub.saldo_kredytu)}</>}
            </span>
          </div>
          {sub.trial_dni != null && (
            <p className="mt-2 text-xs leading-relaxed text-muted">
              {sub.trial_auto_obciazenie ? (
                <>Masz pełny dostęp do wszystkich modułów. Po 14 dniach plan
                  <b className="text-ink"> {ETYKIETA_PLANU[sub.tier] || sub.tier}</b> włączy się automatycznie —
                  obciążymy kartę{sub.karta_ostatnie4 ? <> •••• {sub.karta_ostatnie4}</> : null}. Nie chcesz kontynuować?
                  Anuluj przed końcem triala.</>
              ) : (
                <>Masz teraz pełny dostęp do wszystkich modułów. Po zakończeniu triala lokal przejdzie na plan
                  <b className="text-ink"> Darmowy</b> (rdzeń działa dalej) — wybierz plan poniżej, aby zachować płatne moduły.</>
              )}
            </p>
          )}

          {/* Zmiana planu z dopłatą (proration) */}
          <div className="mt-5 rounded-xl border border-line bg-surface-2 p-4">
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-xs font-semibold text-muted">Zmień plan
                <select value={nowyTier} onChange={(e) => podgladUpgrade(e.target.value)} className={`${fld} w-44`}>
                  <option value="">— wybierz pakiet —</option>
                  {['free', 'basic', 'pro', 'premium', 'enterprise'].filter((t) => t !== sub.tier)
                    .map((t) => <option key={t} value={t}>{ETYKIETA_PLANU[t]}</option>)}
                </select>
              </label>
              <Button variant="ghost" onClick={odnow} disabled={busy}>Odnów abonament</Button>
            </div>
            {podglad && podglad.kierunek === 'upgrade' && (
              <p className="mt-3 text-sm text-ink">
                Dopłata za pozostałe {podglad.pozostale_dni} dni: <b>{zl(podglad.doplata_brutto)}</b> brutto
                <span className="text-muted"> (netto {zl(podglad.doplata_netto)}); od następnego okresu {zl(sub.cena_brutto && podglad.nowa_cena_pelna_netto * 1.23)} brutto/mc.</span>
                <Button className="ml-3" onClick={wykonajUpgrade} disabled={busy}>Zmień i dopłać</Button>
              </p>
            )}
            {podglad && podglad.kierunek === 'downgrade' && (
              <p className="mt-3 text-sm text-ink">
                Obniżka planu — kredyt <b>{zl(podglad.kredyt_netto)}</b> netto trafi na saldo (pomniejszy kolejną płatność).
                <Button className="ml-3" variant="ghost" onClick={wykonajUpgrade} disabled={busy}>Obniż plan</Button>
              </p>
            )}
            {platnoscSub && (
              <div className="mt-3 rounded-lg border border-mint/30 bg-mint/[0.07] px-3 py-2 text-sm">
                Płatność {zl(platnoscSub.brutto)} brutto gotowa.{' '}
                <a href={platnoscSub.link} className="font-semibold text-mint">Otwórz link →</a>
                <span className="mx-2 text-muted">|</span>
                <button onClick={oplacSandbox} className="font-semibold text-ink underline">oznacz opłaconą (sandbox)</button>
              </div>
            )}
          </div>

          <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted/70">Ręczne (operator)</p>
          <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-3">
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

      <Card className="p-6 sm:p-8">
        <SectionHeader title="Dane do faktury" subtitle="Dane Twojej firmy jako nabywcy faktur za subskrypcję (KSeF). Uzupełnij NIP — bez niego faktura jest niekompletna. Zapisujesz przyciskiem „Zapisz ustawienia” na dole." />
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-muted">NIP
            <input value={cfg.faktura_nip || ''} onChange={(e) => set('faktura_nip', e.target.value)} placeholder="1234567890" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Nazwa firmy
            <input value={cfg.faktura_nazwa || ''} onChange={(e) => set('faktura_nazwa', e.target.value)} placeholder={cfg.nazwa_lokalu} className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Adres (ulica i nr)
            <input value={cfg.faktura_adres_l1 || ''} onChange={(e) => set('faktura_adres_l1', e.target.value)} placeholder="ul. Przykładowa 5" className={fld} /></label>
          <label className="text-xs font-semibold text-muted">Kod pocztowy i miasto
            <input value={cfg.faktura_adres_l2 || ''} onChange={(e) => set('faktura_adres_l2', e.target.value)} placeholder="00-123 Warszawa" className={fld} /></label>
        </div>
      </Card>

      {faktury && (
        <Card className="p-6 sm:p-8">
          <SectionHeader title="Faktury za subskrypcję"
            subtitle={`Wystawiane po opłaceniu (KSeF: ${faktury.tryb_ksef === 'stub' ? 'tryb testowy — numery mockowane' : faktury.tryb_ksef}). Pobierz XML FA(3) do archiwum.`} />
          {faktury.faktury.length === 0 ? (
            <p className="mt-4 rounded-xl border border-line bg-white/[0.02] px-4 py-3 text-sm text-muted">
              Brak faktur — pojawią się po pierwszej opłaconej płatności (odnowienie / dopłata).
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="bg-surface-2 text-[11px] uppercase tracking-wide text-muted">
                    <th className="px-3 py-2 text-left font-bold">Numer</th>
                    <th className="px-3 py-2 text-left font-bold">Data</th>
                    <th className="px-3 py-2 text-right font-bold">Brutto</th>
                    <th className="px-3 py-2 text-left font-bold">KSeF</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {faktury.faktury.map((f) => (
                    <tr key={f.id} className="border-t border-line/60">
                      <td className="px-3 py-2 font-semibold text-ink">{f.numer}</td>
                      <td className="px-3 py-2 text-muted">{f.data_wystawienia}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{zl(f.brutto)}</td>
                      <td className="px-3 py-2">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          f.status_ksef === 'przyjeta' ? 'bg-mint/15 text-mint' : f.status_ksef === 'blad' ? 'bg-danger/15 text-danger' : 'bg-white/10 text-muted'}`}>
                          {f.status_ksef}{f.ksef_number ? ` · ${f.ksef_number}` : ''}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => pobierzFakture(f)} className="text-xs font-semibold text-mint">XML</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <div className="flex justify-end">
        <Button onClick={zapisz} disabled={busy}><Icon name="check" className="h-4 w-4" /> Zapisz ustawienia</Button>
      </div>
    </div>
  )
}
