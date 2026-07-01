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

const TABS = [
  { id: 'pulpit', label: 'Pulpit', icon: 'sparkles', group: 'Pulpit', title: 'Pulpit właściciela', Comp: Pulpit },
  { id: 'prognoza-obsady', label: 'Prognoza obsady', icon: 'clock', group: 'Pulpit', title: 'Prognoza obsady', Comp: PrognozaObsady },
  { id: 'pracownicy', label: 'Pracownicy', icon: 'users', group: 'Zarządzanie', title: 'Zarządzanie pracownikami', Comp: Pracownicy },
  { id: 'stanowiska', label: 'Stanowiska', icon: 'office', group: 'Zarządzanie', title: 'Struktura i stanowiska', Comp: Stanowiska },
  { id: 'wymagania', label: 'Wymagania (plan)', icon: 'clipboard', group: 'Zarządzanie', title: 'Planowanie zmian', Comp: Wymagania },
  { id: 'konta', label: 'Konta pracowników', icon: 'key', group: 'Zarządzanie', title: 'Konta i dostęp', Comp: Konta },
  { id: 'ustawienia', label: 'Ustawienia lokalu', icon: 'office', group: 'Zarządzanie', title: 'Ustawienia lokalu', Comp: Ustawienia },
  { id: 'imprezy', label: 'Baza imprez (NAS)', icon: 'server', group: 'Operacje', title: 'Baza imprez — serwer NAS', Comp: Imprezy, modul: 'modul_imprezy' },
  { id: 'dyspozycje', label: 'Dyspozycyjność', icon: 'calendar', group: 'Operacje', title: 'Dyspozycyjność pracowników', Comp: Dyspozycje },
  { id: 'urlopy', label: 'Urlopy', icon: 'calendar', group: 'Operacje', title: 'Wnioski urlopowe', Comp: Urlopy },
  { id: 'grafik', label: 'Interaktywny grafik', icon: 'calendar', group: 'Operacje', title: 'Interaktywny grafik pracy', Comp: Grafik },
  { id: 'gielda', label: 'Giełda zmian', icon: 'clipboard', group: 'Operacje', title: 'Giełda wymiany zmian', Comp: GieldaZmian },
  { id: 'sprzatanie', label: 'Sprzątanie sal', icon: 'check', group: 'Operacje', title: 'Grafik sprzątania sal', Comp: Sprzatanie, modul: 'modul_sprzatanie' },
  { id: 'zamowienia', label: 'Zamówienia', icon: 'clipboard', group: 'Operacje', title: 'Zamówienia sprzątaczki', Comp: Zamowienia },
  { id: 'godziny', label: 'Raport godzin', icon: 'clock', group: 'Operacje', title: 'Raport przepracowanych godzin', Comp: RaportGodzin },
  { id: 'kalendarz', label: 'Kalendarz imprez', icon: 'calendar', group: 'Operacje', title: 'Kalendarz imprez', Comp: KalendarzImprez, modul: 'modul_imprezy' },
  { id: 'zadatki', label: 'Zadatki', icon: 'clipboard', group: 'Operacje', title: 'Zadatki (KP) — przypisania', Comp: Zadatki, modul: 'modul_imprezy' },
  { id: 'zeszyt', label: 'Zeszyt', icon: 'clipboard', group: 'Operacje', title: 'Zeszyt kasowy', Comp: ZeszytPanel, modul: 'modul_rozliczenia' },
  { id: 'rozliczenia', label: 'Rozliczenia kelnerów', icon: 'clipboard', group: 'Operacje', title: 'Rozliczenia kelnerów — podgląd', Comp: RozliczeniaPodglad, modul: 'modul_rozliczenia' },
  { id: 'stoly', label: 'Stoły (live)', icon: 'pin', group: 'Operacje', title: 'Zajętość stołów na żywo', Comp: StolyLive, modul: 'modul_pos' },
  { id: 'rezerwacje', label: 'Rezerwacje (ruch)', icon: 'calendar', group: 'Operacje', title: 'Rezerwacje — ruch (30 dni)', Comp: Rezerwacje },
  { id: 'rezerwacje-stolik', label: 'Rezerwacje stolików', icon: 'pin', group: 'Operacje', title: 'Rezerwacje stolików', Comp: RezerwacjeStolik, modul: 'modul_rezerwacje' },
  { id: 'plan-sali', label: 'Plan sali', icon: 'office', group: 'Operacje', title: 'Plan sali — rozmieszczenie stolików', Comp: PlanSali, modul: 'modul_rezerwacje' },
  { id: 'crm-goscie', label: 'Goście (CRM)', icon: 'users', group: 'Operacje', title: 'Goście — CRM i ryzyko no-show', Comp: CrmGoscie, modul: 'modul_rezerwacje' },
  { id: 'eksport', label: 'Eksport do Excela', icon: 'download', group: 'Operacje', title: 'Eksport danych', Comp: Eksport },
]

const GROUPS = ['Pulpit', 'Zarządzanie', 'Operacje']
// Znacznik wersji = czas builda (wstrzykiwany przez Vite define). Fallback „dev" w trybie
// deweloperskim — żeby brak define nie wywalał komponentu.
const BUILD = typeof __BUILD_TIME__ !== 'undefined' ? __BUILD_TIME__ : 'dev'

export default function Dashboard() {
  const { user, logout } = useAuth()
  const { nazwa_lokalu } = useBranding()
  const [active, setActive] = useState('pulpit')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [cfg, setCfg] = useState({})
  // Konfiguracja lokalu — chowamy zakładki wyłączonych modułów (np. modul_rezerwacje).
  useEffect(() => { api('/lokal/config').then(setCfg).catch(() => {}) }, [])
  const visibleTabs = TABS.filter((t) => !t.modul || cfg[t.modul])
  const current = TABS.find((t) => t.id === active)
  const Active = current.Comp

  const select = (id) => {
    setActive(id)
    setMobileOpen(false)
  }

  return (
    <div className="relative flex h-dvh overflow-hidden bg-bg">
      {/* Dekoracyjna pastelowa poświata w tle (subtelna) */}
      <div aria-hidden className="pointer-events-none fixed -right-40 -top-40 h-96 w-96 rounded-full bg-page-glow opacity-[0.07] blur-2xl transform-gpu" />
      <div aria-hidden className="pointer-events-none fixed -bottom-40 left-40 h-80 w-80 rounded-full bg-mint opacity-[0.05] blur-2xl transform-gpu" />

      {/* Tło pod szufladę (mobile) */}
      {mobileOpen && <div className="fixed inset-0 z-30 animate-overlay-in bg-black/50 backdrop-blur-sm lg:hidden" onClick={() => setMobileOpen(false)} />}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 transform flex-col border-r border-line bg-bg-2/95 backdrop-blur transition-transform duration-300 ease-drawer lg:static lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="flex min-h-[5rem] items-center gap-3 border-b border-line px-7 pt-safe">
          <Logo className="h-8" variant="gradient" />
          <h1 className="font-display text-xl font-bold tracking-tight text-ink">{nazwa_lokalu}</h1>
        </div>

        {/* Nawigacja */}
        <nav className="flex-1 space-y-6 overflow-y-auto px-4 py-6">
          {GROUPS.map((group) => (
            <div key={group}>
              <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-wider text-muted/70">{group}</div>
              <div className="space-y-1">
                {visibleTabs.filter((t) => t.group === group).map((t) => {
                  const on = t.id === active
                  return (
                    <button
                      key={t.id}
                      onClick={() => select(t.id)}
                      aria-current={on ? 'page' : undefined}
                      className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold transition ${
                        on ? 'bg-accent-gradient text-bg shadow-glow' : 'text-muted hover:bg-white/[0.05] hover:text-ink'
                      }`}
                    >
                      <Icon name={t.icon} className="h-5 w-5" strokeWidth={on ? 2.2 : 2} />
                      {t.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Status */}
        <div className="border-t border-line p-4">
          <div className="flex items-center gap-2 rounded-xl border border-line bg-white/[0.03] px-4 py-3">
            <span className="h-2 w-2 animate-pulse rounded-full bg-success" />
            <span className="text-xs font-medium text-muted">Wersja: {BUILD}{BUILD !== 'dev' ? ' UTC' : ''}</span>
          </div>
        </div>
      </aside>

      {/* Główna kolumna */}
      <div className="relative z-10 flex flex-1 flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-line bg-bg-2/60 px-5 pt-[calc(env(safe-area-inset-top)+0.9rem)] pb-[0.9rem] backdrop-blur md:px-8">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileOpen(true)}
              className="rounded-lg border border-line p-2 text-muted transition hover:text-ink lg:hidden"
              aria-label="Otwórz menu"
            >
              <Icon name="menu" className="h-5 w-5" />
            </button>
            <h2 className="font-display text-lg font-bold text-ink md:text-xl">{current.title}</h2>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm font-medium text-muted sm:inline">{user?.login} · administrator</span>
            <PushButton />
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

        <main className="flex-1 overflow-y-auto p-5 md:p-8">
          <div key={active} className="mx-auto w-full max-w-7xl animate-fade-up">
            <Active />
          </div>
        </main>
      </div>
    </div>
  )
}
