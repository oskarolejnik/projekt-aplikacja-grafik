import { useState } from 'react'
import { Icon } from './lib/icons'
import { Logo } from './components/Logo'
import { useAuth } from './context/AuthContext'
import Pracownicy from './components/tabs/Pracownicy'
import Stanowiska from './components/tabs/Stanowiska'
import Wymagania from './components/tabs/Wymagania'
import Konta from './components/tabs/Konta'
import Imprezy from './components/tabs/Imprezy'
import Dyspozycje from './components/tabs/Dyspozycje'
import Grafik from './components/tabs/Grafik'
import Eksport from './components/tabs/Eksport'

const TABS = [
  { id: 'pracownicy', label: 'Pracownicy', icon: 'users', group: 'Zarządzanie', title: 'Zarządzanie pracownikami', Comp: Pracownicy },
  { id: 'stanowiska', label: 'Stanowiska', icon: 'office', group: 'Zarządzanie', title: 'Struktura i stanowiska', Comp: Stanowiska },
  { id: 'wymagania', label: 'Wymagania (plan)', icon: 'clipboard', group: 'Zarządzanie', title: 'Planowanie zmian', Comp: Wymagania },
  { id: 'konta', label: 'Konta pracowników', icon: 'key', group: 'Zarządzanie', title: 'Konta i dostęp', Comp: Konta },
  { id: 'imprezy', label: 'Baza imprez (NAS)', icon: 'server', group: 'Operacje', title: 'Baza imprez — serwer NAS', Comp: Imprezy },
  { id: 'dyspozycje', label: 'Dyspozycyjność', icon: 'calendar', group: 'Operacje', title: 'Dyspozycyjność pracowników', Comp: Dyspozycje },
  { id: 'grafik', label: 'Interaktywny grafik', icon: 'calendar', group: 'Operacje', title: 'Interaktywny grafik pracy', Comp: Grafik },
  { id: 'eksport', label: 'Eksport do Excela', icon: 'download', group: 'Operacje', title: 'Eksport danych', Comp: Eksport },
]

const GROUPS = ['Zarządzanie', 'Operacje']

export default function Dashboard() {
  const { user, logout } = useAuth()
  const [active, setActive] = useState('pracownicy')
  const [mobileOpen, setMobileOpen] = useState(false)
  const current = TABS.find((t) => t.id === active)
  const Active = current.Comp

  const select = (id) => {
    setActive(id)
    setMobileOpen(false)
  }

  return (
    <div className="relative flex h-dvh overflow-hidden bg-bg">
      {/* Dekoracyjna pastelowa poświata w tle (subtelna) */}
      <div aria-hidden className="pointer-events-none fixed -right-40 -top-40 h-96 w-96 rounded-full bg-page-glow opacity-[0.07] blur-3xl" />
      <div aria-hidden className="pointer-events-none fixed -bottom-40 left-40 h-80 w-80 rounded-full bg-mint opacity-[0.05] blur-3xl" />

      {/* Tło pod szufladę (mobile) */}
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm lg:hidden" onClick={() => setMobileOpen(false)} />}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 transform flex-col border-r border-line bg-bg-2/95 backdrop-blur transition-transform duration-300 lg:static lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="flex h-20 items-center gap-3 border-b border-line px-7">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent-gradient">
            <Logo className="h-5" variant="bg" />
          </div>
          <h1 className="font-display text-xl font-bold tracking-tight text-ink">
            Grafik<span className="text-gradient">Pro</span>
          </h1>
        </div>

        {/* Nawigacja */}
        <nav className="flex-1 space-y-6 overflow-y-auto px-4 py-6">
          {GROUPS.map((group) => (
            <div key={group}>
              <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-wider text-muted/70">{group}</div>
              <div className="space-y-1">
                {TABS.filter((t) => t.group === group).map((t) => {
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
            <span className="text-xs font-medium text-muted">Wersja Premium</span>
          </div>
        </div>
      </aside>

      {/* Główna kolumna */}
      <div className="relative z-10 flex flex-1 flex-col overflow-hidden">
        <header className="flex h-20 shrink-0 items-center justify-between border-b border-line bg-bg-2/60 px-5 backdrop-blur md:px-8">
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
          <div className="mx-auto w-full max-w-7xl animate-fade-in">
            <Active />
          </div>
        </main>
      </div>
    </div>
  )
}
