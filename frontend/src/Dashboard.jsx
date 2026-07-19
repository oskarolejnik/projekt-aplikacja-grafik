/* global __BUILD_TIME__ */
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from './lib/icons'
import { Logo } from './components/Logo'
import { PushButton } from './components/PushButton'
import { useAuth } from './context/AuthContext'
import { useBranding } from './context/BrandingContext'
import { api } from './lib/api'
import { LazyErrorBoundary, LazyFallback } from './components/ui/LazyFallback'
import {
  clearReservationRoute,
  navigateReservationRoute,
  readReservationRoute,
  subscribeReservationRoute,
} from './lib/reservationRoute'
import { readReservationSession, reservationHistoryState } from './lib/reservationSession'
import { confirmReservationLeave, hasReservationLeaveGuard } from './lib/reservationLeaveGuard'

const loadPulpit = () => import('./components/tabs/Pulpit')
const loadPrognozaObsady = () => import('./components/tabs/PrognozaObsady')
const loadPracownicy = () => import('./components/tabs/Pracownicy')
const loadStanowiska = () => import('./components/tabs/Stanowiska')
const loadKonta = () => import('./components/tabs/Konta')
const loadGrafikWorkspace = () => import('./components/tabs/GrafikWorkspace')
const loadSprzatanie = () => import('./components/tabs/Sprzatanie')
const loadZamowienia = () => import('./components/tabs/Zamowienia')
const loadUrlopy = () => import('./components/tabs/Urlopy')
const loadRaportGodzin = () => import('./components/tabs/RaportGodzin')
const loadRozliczeniaPodglad = () => import('./components/tabs/RozliczeniaPodglad')
const loadZeszytPanel = () => import('./components/tabs/ZeszytPanel')
const loadKalendarzImprez = () => import('./components/tabs/KalendarzImprez')
const loadStolyLive = () => import('./components/tabs/StolyLive')
const loadReservationsWorkspace = () => import('./components/tabs/ReservationsWorkspace')
const loadAnalitykaRezerwacji = () => import('./components/tabs/AnalitykaRezerwacji')
const loadCrmGoscie = () => import('./components/tabs/CrmGoscie')
const loadGieldaZmian = () => import('./components/tabs/GieldaZmian')
const loadUstawienia = () => import('./components/tabs/Ustawienia')
const loadEksport = () => import('./components/tabs/Eksport')
const loadOgloszenia = () => import('./components/tabs/Ogloszenia')
const loadNapiwki = () => import('./components/tabs/Napiwki')
const loadZgodnosc = () => import('./components/tabs/Zgodnosc')
const loadZapytaniaImprez = () => import('./components/tabs/ZapytaniaImprez')
const loadAntyfraudPos = () => import('./components/tabs/AntyfraudPos')
const loadUtargPos = () => import('./components/tabs/UtargPos')
const loadFlota = () => import('./components/tabs/Flota')

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
  { id: 'pulpit', label: 'Pulpit', icon: 'sparkles', kat: 'pulpit', title: 'Pulpit właściciela', load: loadPulpit },
  { id: 'prognoza-obsady', label: 'Prognoza obsady', icon: 'clock', kat: 'pulpit', title: 'Prognoza obsady', load: loadPrognozaObsady },
  // Zespół — ludzie, konta, komunikacja, formalności.
  { id: 'pracownicy', label: 'Pracownicy', icon: 'users', kat: 'zespol', title: 'Zarządzanie pracownikami', load: loadPracownicy },
  { id: 'stanowiska', label: 'Stanowiska', icon: 'office', kat: 'zespol', title: 'Struktura i stanowiska', load: loadStanowiska },
  { id: 'konta', label: 'Konta pracowników', icon: 'key', kat: 'zespol', title: 'Konta i dostęp', load: loadKonta },
  { id: 'urlopy', label: 'Urlopy', icon: 'calendar', kat: 'zespol', title: 'Wnioski urlopowe', load: loadUrlopy },
  { id: 'ogloszenia', label: 'Ogłoszenia', icon: 'bell', kat: 'zespol', title: 'Ogłoszenia dla zespołu', load: loadOgloszenia },
  { id: 'zgodnosc', label: 'Zgodność', icon: 'clipboard', kat: 'zespol', title: 'Zgodność — badania i terminy', load: loadZgodnosc },
  // Grafik — planowanie i rozliczanie czasu pracy.
  { id: 'grafik', label: 'Grafik pracy', icon: 'calendar', kat: 'grafik', title: 'Planowanie grafiku', load: loadGrafikWorkspace },
  { id: 'gielda', label: 'Giełda zmian', icon: 'refresh', kat: 'grafik', title: 'Giełda wymiany zmian', load: loadGieldaZmian },
  { id: 'godziny', label: 'Raport godzin', icon: 'clock', kat: 'grafik', title: 'Raport przepracowanych godzin', load: loadRaportGodzin },
  { id: 'sprzatanie', label: 'Sprzątanie sal', icon: 'check', kat: 'grafik', title: 'Grafik sprzątania sal', load: loadSprzatanie, modul: 'modul_sprzatanie' },
  { id: 'zamowienia', label: 'Zamówienia', icon: 'clipboard', kat: 'grafik', title: 'Zamówienia sprzątaczki', load: loadZamowienia },
  // Kasa i POS — pieniądze i sygnały z kasy.
  { id: 'utarg-pos', label: 'Utarg (POS)', icon: 'upload', kat: 'kasa', title: 'Utarg dnia — źródła POS', load: loadUtargPos },
  { id: 'zeszyt', label: 'Kasa dnia', icon: 'clipboard', kat: 'kasa', title: 'Kasa dnia — zeszyt i rozliczenie', load: loadZeszytPanel, modul: 'modul_rozliczenia' },
  { id: 'rozliczenia', label: 'Rozliczenia kelnerów', icon: 'clipboard', kat: 'kasa', title: 'Rozliczenia kelnerów — podgląd', load: loadRozliczeniaPodglad, modul: 'modul_rozliczenia' },
  { id: 'napiwki', label: 'Napiwki', icon: 'sparkles', kat: 'kasa', title: 'Napiwki — podział między obsługę', load: loadNapiwki },
  { id: 'stoly', label: 'Stoły (live)', icon: 'pin', kat: 'kasa', title: 'Zajętość stołów na żywo', load: loadStolyLive, modul: 'modul_pos' },
  { id: 'antyfraud', label: 'Antyfraud POS', icon: 'warning', kat: 'kasa', title: 'Antyfraud POS — storna i rabaty', load: loadAntyfraudPos, modul: 'modul_pos', tierModul: 'modul_antyfraud' },
  { id: 'eksport', label: 'Eksport do Excela', icon: 'download', kat: 'kasa', title: 'Eksport danych', load: loadEksport },
  // Goście — rezerwacje i relacje.
  { id: 'rezerwacje', label: 'Rezerwacje', icon: 'calendar', kat: 'goscie', title: 'Rezerwacje', load: loadReservationsWorkspace, modul: 'modul_rezerwacje' },
  { id: 'crm-goscie', label: 'Baza gości', icon: 'users', kat: 'goscie', title: 'Baza gości', load: loadCrmGoscie, modul: 'modul_rezerwacje' },
  { id: 'analityka-rezerwacji', label: 'Wyniki rezerwacji', icon: 'sparkles', kat: 'goscie', title: 'Wyniki rezerwacji', load: loadAnalitykaRezerwacji, modul: 'modul_rezerwacje' },
  // Imprezy — eventy i zapytania. Rozliczenia wydarzeń pozostają w kalendarzu imprez.
  { id: 'kalendarz', label: 'Kalendarz imprez', icon: 'calendar', kat: 'imprezy', title: 'Kalendarz imprez', load: loadKalendarzImprez, modul: 'modul_imprezy' },
  { id: 'zapytania-imprez', label: 'Zapytania o imprezy', icon: 'sparkles', kat: 'imprezy', title: 'Zapytania o imprezy', load: loadZapytaniaImprez, modul: 'modul_imprezy' },
  // Operator (instancja-matka) — panel floty; widoczny tylko gdy /api/flota → enabled.
  { id: 'flota', label: 'Flota lokali', icon: 'server', kat: 'operator', title: 'Flota lokali — operator', load: loadFlota, operator: true },
  // Ustawienia — poza kategoriami (przycisk przy profilu / wpis pod akordeonami).
  { id: 'ustawienia', label: 'Ustawienia lokalu', icon: 'office', kat: 'ustawienia', title: 'Ustawienia lokalu', load: loadUstawienia },
]

const TAB_BY_ID = new Map(TABS.map((tab) => [tab.id, tab]))

// Prefetch dopiero po realnym sygnale intencji. Dynamic import i runtime cache
// pobierają wyłącznie widok wskazany kursorem albo fokusem klawiatury.
function prefetchTab(id) {
  const request = TAB_BY_ID.get(id)?.load?.()
  request?.catch(() => {}) // klik nadal pokaże odzyskiwalny LazyErrorBoundary
}

// Znacznik wersji = czas builda (wstrzykiwany przez Vite define). Fallback „dev" w trybie
// deweloperskim — żeby brak define nie wywalał komponentu.
const BUILD = typeof __BUILD_TIME__ !== 'undefined' ? __BUILD_TIME__ : 'dev'

export default function Dashboard() {
  const { user, logout } = useAuth()
  const reservationHistory = reservationHistoryState(user)
  const { nazwa_lokalu } = useBranding()
  const [active, setActive] = useState(() => readReservationRoute()
    ? 'rezerwacje'
    : 'pulpit')
  const [openCat, setOpenCat] = useState(null)     // dropdown kategorii (desktop)
  const [openAcc, setOpenAcc] = useState('pulpit') // rozwinięty akordeon (mobile)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [settingsSection, setSettingsSection] = useState('lokal')
  const [cfg, setCfg] = useState({})
  const [cfgReady, setCfgReady] = useState(false)
  const [flotaEnabled, setFlotaEnabled] = useState(false)   // panel operatora tylko na matce
  const [sub, setSub] = useState(null)                      // stan subskrypcji (baner grace/blokada)
  const [lazyAttempt, setLazyAttempt] = useState(0)
  const mobileMenuButtonRef = useRef(null)
  const mobileDrawerRef = useRef(null)
  const reservationLeaveBypassRef = useRef(false)
  const reservationLeaveFlowRef = useRef(null)
  // Konfiguracja lokalu — chowamy zakładki wyłączonych modułów (np. modul_rezerwacje).
  useEffect(() => {
    let mounted = true
    api('/lokal/config')
      .then((value) => { if (mounted) setCfg(value) })
      .catch(() => {})
      .finally(() => { if (mounted) setCfgReady(true) })
    return () => { mounted = false }
  }, [])
  useEffect(() => { api('/subskrypcja').then(setSub).catch(() => {}) }, [])
  // Zakładka „Flota" pojawia się tylko na instancji-matce (samoobsługa włączona).
  useEffect(() => { api('/flota').then((f) => setFlotaEnabled(!!f.enabled)).catch(() => {}) }, [])

  // Zakładka modułu widoczna, gdy moduł WŁĄCZONY w configu I ODBLOKOWANY w planie (tier/trial).
  // Dopóki subskrypcja się nie wczyta (dostepne=undefined) nie chowamy — unikamy migotania.
  const dostepne = sub?.dostepne_moduly
  const modulOk = (m) => cfg[m] && (!dostepne || dostepne.includes(m))
  // tierModul = wirtualny moduł tier-only (bez flagi w cfg), np. antyfraud = Premium na modul_pos
  const tierOk = (m) => !m || !dostepne || dostepne.includes(m)
  const visibleTabs = TABS.filter((t) => (!t.modul || modulOk(t.modul)) && tierOk(t.tierModul) && (!t.operator || flotaEnabled))
  const kategorie = KATEGORIE.filter((k) => visibleTabs.some((t) => t.kat === k.id))
  const requested = TABS.find((t) => t.id === active) || TAB_BY_ID.get('pulpit')
  const requestedVisible = visibleTabs.some((tab) => tab.id === requested.id)
  const current = requested.modul && (!cfgReady || !requestedVisible)
    ? TAB_BY_ID.get('pulpit')
    : requested
  const Active = useMemo(() => lazy(current.load), [current.load, lazyAttempt])
  const aktywnaKat = current.kat

  // Escape zamyka dropdown. Mobilna szuflada ma własny kontrakt fokusu poniżej.
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') setOpenCat(null) }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [])

  useEffect(() => subscribeReservationRoute((reservationRoute, event) => {
    if (reservationRoute) {
      setActive('rezerwacje')
      const flow = reservationLeaveFlowRef.current
      if (flow) {
        flow.restored = true
        if (flow.decision !== null) {
          reservationLeaveFlowRef.current = null
          if (flow.decision) {
            reservationLeaveBypassRef.current = true
            window.history.back()
          }
        }
      }
      return
    }

    if (event?.type === 'popstate' && reservationLeaveBypassRef.current) {
      reservationLeaveBypassRef.current = false
    } else if (event?.type === 'popstate' && hasReservationLeaveGuard()) {
      if (!reservationLeaveFlowRef.current) {
        const flow = { restored: false, decision: null }
        reservationLeaveFlowRef.current = flow
        window.history.forward()
        void confirmReservationLeave().then((decision) => {
          if (reservationLeaveFlowRef.current !== flow) return
          flow.decision = decision
          if (!flow.restored) return
          reservationLeaveFlowRef.current = null
          if (decision) {
            reservationLeaveBypassRef.current = true
            window.history.back()
          }
        })
      }
      return
    }
    // Back zmienia hash dwoma zdarzeniami. Pusty `hashchange` pomiędzy
    // `popstate` i odtworzonym wpisem nie może odmontować chronionego workspace.
    if (reservationLeaveFlowRef.current) return
    const restored = window.history.state?.lokaloDashboardTab
    setActive(TAB_BY_ID.has(restored) ? restored : 'pulpit')
  }), [])

  useEffect(() => {
    if (!cfgReady || active !== 'rezerwacje' || requestedVisible) return
    clearReservationRoute({ replace: true, state: { lokaloDashboardTab: 'pulpit' } })
    setActive('pulpit')
  }, [active, cfgReady, requestedVisible])
  // Otwarta szuflada startuje z rozwiniętą kategorią bieżącej zakładki.
  useEffect(() => { if (mobileOpen) setOpenAcc(aktywnaKat) }, [mobileOpen]) // eslint-disable-line react-hooks/exhaustive-deps

  // Szuflada działa jak modal: blokuje tło, utrzymuje fokus, zamyka się przez Escape
  // i oddaje fokus do przycisku menu. Ten sam przewidywalny kontrakt ma arkusz pracownika.
  useEffect(() => {
    if (!mobileOpen) return
    const drawer = mobileDrawerRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const focusable = () => Array.from(drawer?.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) || [])
    focusable()[0]?.focus()

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setMobileOpen(false)
        return
      }
      if (event.key !== 'Tab') return
      const elements = focusable()
      if (elements.length === 0) return
      const first = elements[0]
      const last = elements[elements.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      if (mobileMenuButtonRef.current?.isConnected) mobileMenuButtonRef.current.focus()
    }
  }, [mobileOpen])

  // Po przejściu do układu desktopowego ukryta szuflada nie może nadal blokować strony.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const desktop = window.matchMedia('(min-width: 1024px)')
    const onBreakpoint = (event) => {
      if (event.matches) setMobileOpen(false)
    }
    if (desktop.addEventListener) desktop.addEventListener('change', onBreakpoint)
    else desktop.addListener?.(onBreakpoint)
    return () => {
      if (desktop.removeEventListener) desktop.removeEventListener('change', onBreakpoint)
      else desktop.removeListener?.(onBreakpoint)
    }
  }, [])

  const select = async (id, section) => {
    if (id !== 'rezerwacje' && readReservationRoute() && hasReservationLeaveGuard()) {
      const leave = await confirmReservationLeave()
      if (!leave) return
    }
    if (id === 'ustawienia' && section) setSettingsSection(section)
    if (id === 'rezerwacje') {
      if (!readReservationRoute()) {
        window.history.replaceState({
          ...(window.history.state || {}),
          lokaloDashboardTab: active,
        }, '', window.location.href)
        navigateReservationRoute(readReservationSession(user)?.route || { view: 'today' }, {
          state: {
            lokaloDashboardTab: 'rezerwacje',
            ...reservationHistory,
          },
        })
      }
    } else if (readReservationRoute()) {
      clearReservationRoute({ state: { lokaloDashboardTab: id } })
    } else {
      window.history.replaceState({
        ...(window.history.state || {}),
        lokaloDashboardTab: id,
      }, '', window.location.href)
    }
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
          ref={mobileMenuButtonRef}
          type="button"
          onClick={() => setMobileOpen(true)}
          className="min-h-11 min-w-11 rounded-lg border border-line p-2 text-muted transition hover:text-ink lg:hidden"
          aria-label="Otwórz menu"
          aria-expanded={mobileOpen}
          aria-controls="dashboard-mobile-menu"
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
                  type="button"
                  onClick={() => setOpenCat(otwarta ? null : k.id)}
                  aria-expanded={otwarta}
                  className={`flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
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
                          type="button"
                          key={t.id}
                          onClick={() => select(t.id)}
                          onPointerEnter={() => prefetchTab(t.id)}
                          onFocus={() => prefetchTab(t.id)}
                          aria-current={on ? 'page' : undefined}
                          className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
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
            type="button"
            onClick={() => select('ustawienia')}
            onPointerEnter={() => prefetchTab('ustawienia')}
            onFocus={() => prefetchTab('ustawienia')}
            aria-label="Ustawienia lokalu"
            title="Ustawienia lokalu"
            className={`hidden min-h-11 min-w-11 rounded-xl border border-line p-2 transition lg:block ${
              active === 'ustawienia' ? 'bg-mint/[0.12] text-mint' : 'bg-white/[0.04] text-muted hover:text-ink'
            }`}
          >
            <Icon name="office" className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={logout}
            className="flex min-h-11 min-w-11 items-center gap-2 rounded-xl border border-line bg-white/[0.04] px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink"
            aria-label="Wyloguj"
          >
            <Icon name="logout" className="h-4 w-4" />
            <span className="hidden md:inline">Wyloguj</span>
          </button>
        </div>
      </header>

      {/* ── Szuflada mobile: kategorie jako akordeony ── */}
      {mobileOpen && <div aria-hidden="true" className="fixed inset-0 z-30 animate-overlay-in bg-black/50 backdrop-blur-sm lg:hidden" onClick={() => setMobileOpen(false)} />}
      <aside
        ref={mobileDrawerRef}
        id="dashboard-mobile-menu"
        role="dialog"
        aria-modal={mobileOpen ? 'true' : undefined}
        aria-label="Menu administracyjne"
        aria-hidden={!mobileOpen}
        inert={mobileOpen ? undefined : ''}
        className={`fixed inset-y-0 left-0 z-40 flex w-80 max-w-[85vw] transform flex-col border-r border-white/[0.06] bg-bg/85 backdrop-blur-2xl transition-transform duration-300 ease-drawer lg:hidden ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex min-h-[4.5rem] items-center gap-3 border-b border-line px-6 pt-safe">
          <Logo className="h-8" variant="gradient" />
          <h1 className="min-w-0 truncate font-display text-lg font-bold tracking-tight text-ink">{nazwa_lokalu}</h1>
          <button type="button" onClick={() => setMobileOpen(false)} className="ml-auto min-h-11 min-w-11 rounded-lg p-2 text-muted transition hover:text-ink" aria-label="Zamknij menu">
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
                  type="button"
                  onClick={() => setOpenAcc(otwarta ? null : k.id)}
                  aria-expanded={otwarta}
                  className={`flex min-h-11 w-full items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition ${
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
                          type="button"
                          key={t.id}
                          onClick={() => select(t.id)}
                          onPointerEnter={() => prefetchTab(t.id)}
                          onFocus={() => prefetchTab(t.id)}
                          aria-current={on ? 'page' : undefined}
                          className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition ${
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
            type="button"
            onClick={() => select('ustawienia')}
            onPointerEnter={() => prefetchTab('ustawienia')}
            onFocus={() => prefetchTab('ustawienia')}
            aria-current={active === 'ustawienia' ? 'page' : undefined}
            className={`flex min-h-11 w-full items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition ${
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
            <button
              type="button"
              onClick={() => select('ustawienia', 'plan')}
              onPointerEnter={() => prefetchTab('ustawienia')}
              onFocus={() => prefetchTab('ustawienia')}
              className="ml-auto min-h-11 rounded-lg border border-current px-2.5 py-1 text-xs font-semibold"
            >
              Przejdź do subskrypcji
            </button>
          </div>
        )}
        {sub && sub.trial_dni != null && (
          <div className="mx-auto mb-5 flex w-full max-w-7xl flex-wrap items-center gap-2 rounded-xl border border-mint/40 bg-mint/10 px-4 py-3 text-sm text-mint">
            <Icon name="sparkles" className="h-4 w-4 shrink-0" />
            <span className="font-semibold">
              14 dni za darmo — {sub.trial_dni === 0 ? 'ostatni dzień' : `zostało ${sub.trial_dni} ${sub.trial_dni === 1 ? 'dzień' : 'dni'}`}.
              {sub.trial_auto_obciazenie
                ? <> Po trialu plan włączy się automatycznie{sub.karta_ostatnie4 ? ` (karta •••• ${sub.karta_ostatnie4})` : ''} — anuluj wcześniej, jeśli nie chcesz kontynuować.</>
                : ' Masz pełny dostęp do wszystkich modułów; wybierz plan, żeby ich nie stracić po trialu.'}
            </span>
            <button
              type="button"
              onClick={() => select('ustawienia', 'plan')}
              onPointerEnter={() => prefetchTab('ustawienia')}
              onFocus={() => prefetchTab('ustawienia')}
              className="ml-auto min-h-11 rounded-lg border border-current px-2.5 py-1 text-xs font-semibold"
            >
              {sub.trial_auto_obciazenie ? 'Zarządzaj' : 'Wybierz plan'}
            </button>
          </div>
        )}
        <div key={active} className="mx-auto w-full max-w-7xl animate-fade-up">
          {current.id !== 'rezerwacje' ? <div className="mb-5 flex items-baseline gap-3 md:mb-6">
            {current.kat !== 'ustawienia' && (
              <span className="hidden text-sm font-medium text-muted/70 md:inline">
                {KATEGORIE.find((k) => k.id === current.kat)?.label}
                <span className="mx-2 opacity-50">/</span>
              </span>
            )}
            <h2 className="font-display text-lg font-bold text-ink md:text-xl">{current.title}</h2>
          </div> : null}
          <LazyErrorBoundary
            resetKey={`${active}:${lazyAttempt}`}
            onRetry={() => setLazyAttempt((attempt) => attempt + 1)}
          >
            <Suspense fallback={<LazyFallback compact label={`Ładowanie: ${current.title}`} />}>
              {active === 'ustawienia' ? <Active initialSection={settingsSection} /> : <Active />}
            </Suspense>
          </LazyErrorBoundary>
        </div>
      </main>
    </div>
  )
}
