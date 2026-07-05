/* global __BUILD_TIME__ */
import { useState, useEffect } from 'react'
import { Icon } from './lib/icons'
import { Logo } from './components/Logo'
import { PushButton } from './components/PushButton'
import { useAuth } from './context/AuthContext'
import { useBranding } from './context/BrandingContext'
import { api } from './lib/api'
import Pulpit from './components/tabs/Pulpit'
import PrognozaObsady from './components/tabs/PrognozaObsady'
import Pracownicy from './components/tabs/Pracownicy'
import Stanowiska from './components/tabs/Stanowiska'
import Wymagania from './components/tabs/Wymagania'
import Konta from './components/tabs/Konta'
import Imprezy from './components/tabs/Imprezy'
import Dyspozycje from './components/tabs/Dyspozycje'
import Grafik from './components/tabs/Grafik'
import Sprzatanie from './components/tabs/Sprzatanie'
import Zamowienia from './components/tabs/Zamowienia'
import Urlopy from './components/tabs/Urlopy'
import RaportGodzin from './components/tabs/RaportGodzin'
import RozliczeniaPodglad from './components/tabs/RozliczeniaPodglad'
import ZeszytPanel from './components/tabs/ZeszytPanel'
import KalendarzImprez from './components/tabs/KalendarzImprez'
import Zadatki from './components/tabs/Zadatki'
import StolyLive from './components/tabs/StolyLive'
import Rezerwacje from './components/tabs/Rezerwacje'
import RezerwacjeStolik from './components/tabs/RezerwacjeStolik'
import CrmGoscie from './components/tabs/CrmGoscie'
import GieldaZmian from './components/tabs/GieldaZmian'
import PlanSali from './components/tabs/PlanSali'
import Ustawienia from './components/tabs/Ustawienia'
import Eksport from './components/tabs/Eksport'
import Ogloszenia from './components/tabs/Ogloszenia'
import Napiwki from './components/tabs/Napiwki'
import Zgodnosc from './components/tabs/Zgodnosc'
import ZapytaniaImprez from './components/tabs/ZapytaniaImprez'
import AntyfraudPos from './components/tabs/AntyfraudPos'
import UtargPos from './components/tabs/UtargPos'
import Flota from './components/tabs/Flota'

// Nawigacja dwupoziomowa (feedback: „zakładek jest na tyle, że można się pogubić —
// najpierw główne kategorie, później ładne listy rozwijane"). Na desktopie górny
// pasek kategorii z dropdownami, na mobile szuflada z akordeonami.
const KATEGORIE = [
  { id: 'pulpit', label: 'Pulpit', icon: 'sparkles' },
  { id: 'zespol', label: 'Zespół', icon: 'users' },
  { id: 'grafik', label: 'Grafik', icon: 'calendar' },
  { id: 'kasa', label: 'Kasa i POS', icon: 'clipboard' },
  { id: 'goscie', label: 'Goście', icon: 'pin' },
  { id: 'imprezy', label: 'Imprezy', icon: 'bell' },
  { id: 'operator', label: 'Operator', icon: 'server' },   // tylko na instancji-matce (panel floty)
]

const TABS = [
  // Pulpit — przegląd dnia i prognozy.
  { id: 'pulpit', label: 'Pulpit', icon: 'sparkles', kat: 'pulpit', title: 'Pulpit właściciela', Comp: Pulpit },
  { id: 'prognoza-obsady', label: 'Prognoza obsady', icon: 'clock', kat: 'pulpit', title: 'Prognoza obsady', Comp: PrognozaObsady },
  // Zespół — ludzie, konta, komunikacja, formalności.
  { id: 'pracownicy', label: 'Pracownicy', icon: 'users', kat: 'zespol', title: 'Zarządzanie pracownikami', Comp: Pracownicy },
  { id: 'stanowiska', label: 'Stanowiska', icon: 'office', kat: 'zespol', title: 'Struktura i stanowiska', Comp: Stanowiska },
  { id: 'konta', label: 'Konta pracowników', icon: 'key', kat: 'zespol', title: 'Konta i dostęp', Comp: Konta },
  { id: 'urlopy', label: 'Urlopy', icon: 'calendar', kat: 'zespol', title: 'Wnioski urlopowe', Comp: Urlopy },
  { id: 'ogloszenia', label: 'Ogłoszenia', icon: 'bell', kat: 'zespol', title: 'Ogłoszenia dla zespołu', Comp: Ogloszenia },
  { id: 'zgodnosc', label: 'Zgodność', icon: 'clipboard', kat: 'zespol', title: 'Zgodność — badania i terminy', Comp: Zgodnosc },
  // Grafik — planowanie i rozliczanie czasu pracy.
  { id: 'grafik', label: 'Interaktywny grafik', icon: 'calendar', kat: 'grafik', title: 'Interaktywny grafik pracy', Comp: Grafik },
  { id: 'wymagania', label: 'Wymagania (plan)', icon: 'clipboard', kat: 'grafik', title: 'Planowanie zmian', Comp: Wymagania },
  { id: 'dyspozycje', label: 'Dyspozycyjność', icon: 'calendar', kat: 'grafik', title: 'Dyspozycyjność pracowników', Comp: Dyspozycje },
  { id: 'gielda', label: 'Giełda zmian', icon: 'refresh', kat: 'grafik', title: 'Giełda wymiany zmian', Comp: GieldaZmian },
  { id: 'godziny', label: 'Raport godzin', icon: 'clock', kat: 'grafik', title: 'Raport przepracowanych godzin', Comp: RaportGodzin },
  { id: 'sprzatanie', label: 'Sprzątanie sal', icon: 'check', kat: 'grafik', title: 'Grafik sprzątania sal', Comp: Sprzatanie, modul: 'modul_sprzatanie' },
  { id: 'zamowienia', label: 'Zamówienia', icon: 'clipboard', kat: 'grafik', title: 'Zamówienia sprzątaczki', Comp: Zamowienia },
  // Kasa i POS — pieniądze i sygnały z kasy.
  { id: 'utarg-pos', label: 'Utarg (POS)', icon: 'upload', kat: 'kasa', title: 'Utarg dnia — źródła POS', Comp: UtargPos },
  { id: 'zeszyt', label: 'Zeszyt', icon: 'clipboard', kat: 'kasa', title: 'Zeszyt kasowy', Comp: ZeszytPanel, modul: 'modul_rozliczenia' },
  { id: 'rozliczenia', label: 'Rozliczenia kelnerów', icon: 'clipboard', kat: 'kasa', title: 'Rozliczenia kelnerów — podgląd', Comp: RozliczeniaPodglad, modul: 'modul_rozliczenia' },
  { id: 'napiwki', label: 'Napiwki', icon: 'sparkles', kat: 'kasa', title: 'Napiwki — podział między obsługę', Comp: Napiwki },
  { id: 'stoly', label: 'Stoły (live)', icon: 'pin', kat: 'kasa', title: 'Zajętość stołów na żywo', Comp: StolyLive, modul: 'modul_pos' },
  { id: 'antyfraud', label: 'Antyfraud POS', icon: 'warning', kat: 'kasa', title: 'Antyfraud POS — storna i rabaty', Comp: AntyfraudPos, modul: 'modul_pos' },
  { id: 'eksport', label: 'Eksport do Excela', icon: 'download', kat: 'kasa', title: 'Eksport danych', Comp: Eksport },
  // Goście — rezerwacje i relacje.
  { id: 'rezerwacje-stolik', label: 'Rezerwacje stolików', icon: 'pin', kat: 'goscie', title: 'Rezerwacje stolików', Comp: RezerwacjeStolik, modul: 'modul_rezerwacje' },
  { id: 'plan-sali', label: 'Plan sali', icon: 'office', kat: 'goscie', title: 'Plan sali — rozmieszczenie stolików', Comp: PlanSali, modul: 'modul_rezerwacje' },
  { id: 'crm-goscie', label: 'Goście (CRM)', icon: 'users', kat: 'goscie', title: 'Goście — CRM i ryzyko no-show', Comp: CrmGoscie, modul: 'modul_rezerwacje' },
  { id: 'rezerwacje', label: 'Rezerwacje (ruch)', icon: 'calendar', kat: 'goscie', title: 'Rezerwacje — ruch (30 dni)', Comp: Rezerwacje },
  // Imprezy — eventy, zapytania, zadatki.
  { id: 'kalendarz', label: 'Kalendarz imprez', icon: 'calendar', kat: 'imprezy', title: 'Kalendarz imprez', Comp: KalendarzImprez, modul: 'modul_imprezy' },
  { id: 'zapytania-imprez', label: 'Zapytania o imprezy', icon: 'sparkles', kat: 'imprezy', title: 'Zapytania o imprezy', Comp: ZapytaniaImprez, modul: 'modul_imprezy' },
  { id: 'zadatki', label: 'Zadatki', icon: 'clipboard', kat: 'imprezy', title: 'Zadatki (KP) — przypisania', Comp: Zadatki, modul: 'modul_imprezy' },
  { id: 'imprezy', label: 'Baza imprez (NAS)', icon: 'server', kat: 'imprezy', title: 'Baza imprez — serwer NAS', Comp: Imprezy, modul: 'modul_imprezy' },
  // Operator (instancja-matka) — panel floty; widoczny tylko gdy /api/flota → enabled.
  { id: 'flota', label: 'Flota lokali', icon: 'server', kat: 'operator', title: 'Flota lokali — operator', Comp: Flota, operator: true },
  // Ustawienia — poza kategoriami (przycisk przy profilu / wpis pod akordeonami).
  { id: 'ustawienia', label: 'Ustawienia lokalu', icon: 'office', kat: 'ustawienia', title: 'Ustawienia lokalu', Comp: Ustawienia },
]

// Znacznik wersji = czas builda (wstrzykiwany przez Vite define). Fallback „dev" w trybie
// deweloperskim — żeby brak define nie wywalał komponentu.
const BUILD = typeof __BUILD_TIME__ !== 'undefined' ? __BUILD_TIME__ : 'dev'

export default function Dashboard() {
  const { user, logout } = useAuth()
  const { nazwa_lokalu } = useBranding()
  const [active, setActive] = useState('pulpit')
  const [openCat, setOpenCat] = useState(null)     // dropdown kategorii (desktop)
  const [openAcc, setOpenAcc] = useState('pulpit') // rozwinięty akordeon (mobile)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [cfg, setCfg] = useState({})
  const [flotaEnabled, setFlotaEnabled] = useState(false)   // panel operatora tylko na matce
  const [sub, setSub] = useState(null)                      // stan subskrypcji (baner grace/blokada)
  // Konfiguracja lokalu — chowamy zakładki wyłączonych modułów (np. modul_rezerwacje).
  useEffect(() => { api('/lokal/config').then(setCfg).catch(() => {}) }, [])
  useEffect(() => { api('/subskrypcja').then(setSub).catch(() => {}) }, [])
  // Zakładka „Flota" pojawia się tylko na instancji-matce (samoobsługa włączona).
  useEffect(() => { api('/flota').then((f) => setFlotaEnabled(!!f.enabled)).catch(() => {}) }, [])

  const visibleTabs = TABS.filter((t) => (!t.modul || cfg[t.modul]) && (!t.operator || flotaEnabled))
  const kategorie = KATEGORIE.filter((k) => visibleTabs.some((t) => t.kat === k.id))
  const current = TABS.find((t) => t.id === active)
  const Active = current.Comp
  const aktywnaKat = current.kat

  // Escape zamyka dropdown i szufladę.
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') { setOpenCat(null); setMobileOpen(false) } }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [])
  // Otwarta szuflada startuje z rozwiniętą kategorią bieżącej zakładki.
  useEffect(() => { if (mobileOpen) setOpenAcc(aktywnaKat) }, [mobileOpen]) // eslint-disable-line react-hooks/exhaustive-deps

  const select = (id) => {
    setActive(id)
    setOpenCat(null)
    setMobileOpen(false)
  }

  return (
    <div className="relative flex h-dvh flex-col overflow-hidden bg-bg">
      {/* Światło sceny (Cicha scena v2): statyczne, monochromatyczne — nadaje szkłu głębię. */}
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />

      {/* ── Górny pasek: logo · kategorie (desktop) · profil ── */}
      <header className="relative z-40 flex shrink-0 items-center gap-3 border-b border-white/[0.06] bg-bg/55 px-4 pt-[calc(env(safe-area-inset-top)+0.7rem)] pb-[0.7rem] backdrop-blur-xl md:px-6">
        <button
          onClick={() => setMobileOpen(true)}
          className="rounded-lg border border-line p-2 text-muted transition hover:text-ink lg:hidden"
          aria-label="Otwórz menu"
        >
          <Icon name="menu" className="h-5 w-5" />
        </button>

        <div className="flex min-w-0 items-center gap-2.5" title={`Wersja: ${BUILD}${BUILD !== 'dev' ? ' UTC' : ''}`}>
          <Logo className="h-7 shrink-0" variant="gradient" />
          <span className="hidden truncate font-display text-base font-bold tracking-tight text-ink xl:inline">
            {nazwa_lokalu}
          </span>
        </div>

        {/* Kategorie z dropdownami (desktop). */}
        <nav className="ml-4 hidden flex-1 items-center gap-0.5 lg:flex" aria-label="Nawigacja główna">
          {openCat && <div className="fixed inset-0 z-40 cursor-default" onClick={() => setOpenCat(null)} />}
          {kategorie.map((k) => {
            const otwarta = openCat === k.id
            const zawieraAktywna = aktywnaKat === k.id
            return (
              <div key={k.id} className="relative z-50">
                <button
                  onClick={() => setOpenCat(otwarta ? null : k.id)}
                  aria-expanded={otwarta}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                    zawieraAktywna ? 'font-semibold text-mint' : otwarta ? 'bg-white/[0.06] text-ink' : 'text-muted hover:text-ink'
                  }`}
                >
                  {k.label}
                  <Icon name="chevronDown" className={`h-3.5 w-3.5 opacity-70 transition-transform duration-200 ${otwarta ? 'rotate-180' : ''}`} />
                </button>
                {otwarta && (
                  <div className="absolute left-0 top-full mt-2 w-64 animate-fade-up rounded-2xl border border-line bg-bg/95 p-2 shadow-2xl shadow-black/40 backdrop-blur-2xl">
                    {visibleTabs.filter((t) => t.kat === k.id).map((t) => {
                      const on = t.id === active
                      return (
                        <button
                          key={t.id}
                          onClick={() => select(t.id)}
                          aria-current={on ? 'page' : undefined}
                          className={`flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                            on ? 'bg-mint/[0.12] font-semibold text-mint' : 'text-muted hover:bg-white/[0.05] hover:text-ink'
                          }`}
                        >
                          <Icon name={t.icon} className="h-[18px] w-[18px] shrink-0" strokeWidth={2} />
                          {t.label}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </nav>

        {/* Profil + ustawienia. */}
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-sm font-medium text-muted sm:inline">{user?.login} · administrator</span>
          <PushButton />
          <button
            onClick={() => select('ustawienia')}
            aria-label="Ustawienia lokalu"
            title="Ustawienia lokalu"
            className={`hidden rounded-xl border border-line p-2 transition lg:block ${
              active === 'ustawienia' ? 'bg-mint/[0.12] text-mint' : 'bg-white/[0.04] text-muted hover:text-ink'
            }`}
          >
            <Icon name="office" className="h-4 w-4" />
          </button>
          <button
            onClick={logout}
            className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
            aria-label="Wyloguj"
          >
            <Icon name="logout" className="h-4 w-4" />
            <span className="hidden md:inline">Wyloguj</span>
          </button>
        </div>
      </header>

      {/* ── Szuflada mobile: kategorie jako akordeony ── */}
      {mobileOpen && <div className="fixed inset-0 z-30 animate-overlay-in bg-black/50 backdrop-blur-sm lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-80 max-w-[85vw] transform flex-col border-r border-white/[0.06] bg-bg/85 backdrop-blur-2xl transition-transform duration-300 ease-drawer lg:hidden ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex min-h-[4.5rem] items-center gap-3 border-b border-line px-6 pt-safe">
          <Logo className="h-8" variant="gradient" />
          <h1 className="min-w-0 truncate font-display text-lg font-bold tracking-tight text-ink">{nazwa_lokalu}</h1>
          <button onClick={() => setMobileOpen(false)} className="ml-auto rounded-lg p-2 text-muted transition hover:text-ink" aria-label="Zamknij menu">
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-2 overflow-y-auto px-3 py-4" aria-label="Nawigacja główna">
          {kategorie.map((k) => {
            const otwarta = openAcc === k.id
            const zawieraAktywna = aktywnaKat === k.id
            return (
              <div key={k.id} className={`rounded-2xl transition ${otwarta ? 'bg-white/[0.03]' : ''}`}>
                <button
                  onClick={() => setOpenAcc(otwarta ? null : k.id)}
                  aria-expanded={otwarta}
                  className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition ${
                    zawieraAktywna && !otwarta ? 'text-mint' : 'text-ink'
                  }`}
                >
                  <Icon name={k.icon} className="h-5 w-5 opacity-80" strokeWidth={2} />
                  {k.label}
                  <Icon name="chevronDown" className={`ml-auto h-4 w-4 text-muted transition-transform duration-200 ${otwarta ? 'rotate-180' : ''}`} />
                </button>
                {otwarta && (
                  <div className="space-y-0.5 px-2 pb-2">
                    {visibleTabs.filter((t) => t.kat === k.id).map((t) => {
                      const on = t.id === active
                      return (
                        <button
                          key={t.id}
                          onClick={() => select(t.id)}
                          aria-current={on ? 'page' : undefined}
                          className={`flex w-full items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition ${
                            on ? 'bg-mint/[0.12] font-semibold text-mint' : 'text-muted hover:bg-white/[0.05] hover:text-ink'
                          }`}
                        >
                          <Icon name={t.icon} className="h-[18px] w-[18px] shrink-0" strokeWidth={2} />
                          {t.label}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}

          {/* Ustawienia — pojedynczy wpis pod kategoriami. */}
          <button
            onClick={() => select('ustawienia')}
            aria-current={active === 'ustawienia' ? 'page' : undefined}
            className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition ${
              active === 'ustawienia' ? 'bg-mint/[0.12] text-mint' : 'text-ink hover:bg-white/[0.03]'
            }`}
          >
            <Icon name="office" className="h-5 w-5 opacity-80" strokeWidth={2} />
            Ustawienia lokalu
          </button>
        </nav>

        <div className="border-t border-line p-4">
          <div className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.03] px-4 py-3">
            <span className="h-2 w-2 animate-pulse rounded-full bg-success" />
            <span className="text-xs font-medium text-muted">Wersja: {BUILD}{BUILD !== 'dev' ? ' UTC' : ''}</span>
          </div>
        </div>
      </aside>

      {/* ── Treść ── */}
      <main className="relative z-10 flex-1 overflow-y-auto p-5 md:p-8">
        {sub && sub.stan !== 'aktywna' && (
          <div className={`mx-auto mb-5 flex w-full max-w-7xl flex-wrap items-center gap-2 rounded-xl border px-4 py-3 text-sm ${
            sub.stan === 'grace' ? 'border-lemon/40 bg-lemon/10 text-lemon' : 'border-danger/40 bg-danger/10 text-danger'}`}>
            <Icon name="warning" className="h-4 w-4 shrink-0" />
            <span className="font-semibold">
              {sub.stan === 'grace'
                ? `Faktura po terminie — opłać subskrypcję do ${sub.data_grace}, inaczej instancja przejdzie w tryb tylko do odczytu.`
                : 'Subskrypcja nieopłacona — instancja działa w trybie tylko do odczytu. Opłać, aby odblokować zapisy.'}
            </span>
            <button onClick={() => select('ustawienia')} className="ml-auto rounded-lg border border-current px-2.5 py-1 text-xs font-semibold">
              Przejdź do subskrypcji
            </button>
          </div>
        )}
        <div key={active} className="mx-auto w-full max-w-7xl animate-fade-up">
          <div className="mb-5 flex items-baseline gap-3 md:mb-6">
            {current.kat !== 'ustawienia' && (
              <span className="hidden text-sm font-medium text-muted/70 md:inline">
                {KATEGORIE.find((k) => k.id === current.kat)?.label}
                <span className="mx-2 opacity-50">/</span>
              </span>
            )}
            <h2 className="font-display text-lg font-bold text-ink md:text-xl">{current.title}</h2>
          </div>
          <Active />
        </div>
      </main>
    </div>
  )
}
