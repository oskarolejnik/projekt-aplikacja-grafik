import { lazy, Suspense, useState, useEffect } from 'react'
import { MotionConfig } from 'framer-motion'
import { AuthProvider, useAuth } from './context/AuthContext'
import { BrandingProvider } from './context/BrandingContext'
import { DataProvider } from './context/DataContext'
import { ToastProvider } from './components/ui/Toast'
import { LazyErrorBoundary, LazyFallback } from './components/ui/LazyFallback'
import { api, getApiBase } from './lib/api'
import { jestNatywna } from './lib/platforma'

const Landing = lazy(() => import('./pages/Landing'))
const Dashboard = lazy(() => import('./Dashboard'))
const EmployeeArea = lazy(() => import('./pages/EmployeeArea'))
const SzefView = lazy(() => import('./pages/SzefView'))
const SzefKuchniView = lazy(() => import('./pages/SzefKuchniView'))
const RezerwacjaWidget = lazy(() => import('./pages/RezerwacjaWidget'))
const PortalImprezy = lazy(() => import('./pages/PortalImprezy'))
const Onboarding = lazy(() => import('./pages/Onboarding'))
const Start = lazy(() => import('./pages/Start'))
const Produkt = lazy(() => import('./pages/ProduktPro'))
const Zaproszenie = lazy(() => import('./pages/Zaproszenie'))
const WyborInstancji = lazy(() => import('./pages/WyborInstancji'))
const Dokument = lazy(() => import('./pages/Dokument'))
const WorkstationGate = lazy(() => import('./components/workstation/WorkstationGate'))

// Publiczne „trasy" wykrywane po query param (bez logowania, poza AuthProvider):
//   ?rezerwuj → widget rezerwacji gościa,  ?produkt → strona produktu/cennik (marketing),
//   ?impreza=TOKEN → portal klienta imprezy (para młoda / organizator).
const _params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams()
const isWidget = _params.has('rezerwuj')
const isPortalImprezy = _params.has('impreza')
const isProdukt = _params.has('produkt')
const isLogin = _params.has('login')   // ?login → ekran logowania (landing marketingowy prowadzi tu z „Zaloguj")
const isWorkstation = _params.has('stanowisko') // ?stanowisko → dedykowany PIN gate recepcji
const isStart = _params.has('start')   // ?start → kreator lokalu (świeża instancja) lub rozjazd „co dalej"
const isOnboardingParam = _params.has('onboarding')   // ?onboarding → kreator zawsze (na zajętej instancji: podgląd demo)
const isPolityka = _params.has('polityka')            // ?polityka → publiczna Polityka prywatności
const isRegulamin = _params.has('regulamin')          // ?regulamin → publiczny Regulamin
const zaproszenieToken = _params.get('zaproszenie')   // ?zaproszenie=TOKEN → rejestracja pracownika z linku

// Routing wg stanu zalogowania i roli:
//   brak użytkownika → ekran startowy (z logowaniem)
//   admin            → pełny panel zarządzania
//   employee         → samoobsługa dyspozycyjności
function Routed() {
  const {
    user,
    loading,
    workstationLocked,
    workstationChecking,
    workstationGate,
    workstationVersion,
    unlockWorkstation,
    forgetWorkstation,
    authorizationRefreshing,
    authorizationError,
    retryAuthorization,
    logout,
  } = useAuth()
  const [lockError, setLockError] = useState('')
  const [lockRetryAfter, setLockRetryAfter] = useState(0)
  // Dla niezalogowanego sprawdź, czy instancja jest świeża (0 użytkowników) → kreator zamiast logowania.
  const [onboarding, setOnboarding] = useState(null)   // null = sprawdzam, true/false
  useEffect(() => {
    if (loading || user || workstationLocked || authorizationRefreshing || isWorkstation) return
    api('/onboarding/status').then((s) => setOnboarding(!!s.potrzebny)).catch(() => setOnboarding(false))
  }, [authorizationRefreshing, loading, user, workstationLocked])

  const loadingShell = <LazyFallback label="Sprawdzanie sesji" />
  if (loading) return loadingShell
  if (workstationLocked && !isLogin) {
    const unlock = async (credentials) => {
      setLockError('')
      setLockRetryAfter(0)
      try {
        await unlockWorkstation(credentials)
      } catch (error) {
        setLockRetryAfter(error?.retryAfter || 0)
        setLockError(error?.message || 'Nie udało się odblokować stanowiska. Sprawdź połączenie i spróbuj ponownie.')
      }
    }
    const forget = async () => {
      if (!window.confirm('Usunąć powiązanie tego urządzenia ze stanowiskiem recepcji?')) return
      setLockError('')
      try {
        await forgetWorkstation()
      } catch (error) {
        setLockError(error?.message || 'Nie udało się usunąć powiązania stanowiska.')
      }
    }
    return (
      <WorkstationGate
        station={workstationGate?.station}
        operators={workstationGate?.operators || []}
        currentOperatorId={workstationGate?.operators?.find((operator) => operator.last_used)?.id}
        busy={workstationChecking}
        error={lockError}
        retryAfter={lockRetryAfter}
        onUnlock={unlock}
        onUsePassword={() => window.location.assign(`${window.location.pathname}?login`)}
        onForgetStation={workstationGate ? forget : undefined}
      />
    )
  }
  if (authorizationRefreshing) {
    return (
      <main className="grid min-h-dvh place-items-center bg-bg px-5 py-10 text-ink">
        <section className="w-full max-w-md rounded-3xl border border-line bg-surface p-7 shadow-2xl shadow-black/20 sm:p-9" aria-labelledby="authorization-refresh-title">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-line bg-white/[0.04] text-mint" aria-hidden="true">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" />
          </div>
          <p className="mt-6 text-xs font-semibold uppercase tracking-[0.16em] text-muted">Bezpieczna aktualizacja</p>
          <h1 id="authorization-refresh-title" className="mt-2 font-display text-2xl font-semibold tracking-tight">
            {authorizationError ? 'Nie udało się potwierdzić dostępu' : 'Aktualizuję dostęp'}
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted" role={authorizationError ? 'alert' : 'status'}>
            {authorizationError || 'Sprawdzam aktualną rolę i uprawnienia. Dane operacyjne pozostają ukryte.'}
          </p>
          {authorizationError ? (
            <div className="mt-7 grid gap-3 sm:grid-cols-2">
              <button type="button" onClick={() => retryAuthorization()} className="min-h-12 rounded-xl bg-mint px-4 text-sm font-semibold text-bg transition hover:brightness-105">
                Spróbuj ponownie
              </button>
              <button type="button" onClick={logout} className="min-h-12 rounded-xl border border-line bg-white/[0.025] px-4 text-sm font-semibold text-ink transition hover:bg-white/[0.06]">
                Wyloguj
              </button>
            </div>
          ) : null}
        </section>
      </main>
    )
  }
  if (!user) {
    // Nie blokujemy publicznej strony sprzedażowej spinnerem na czas /onboarding/status —
    // domyślnie (status jeszcze null) renderujemy landing OD RAZU. Kreator pokazujemy dopiero,
    // gdy status potwierdzi świeżą instancję (potrzebny=true) — rzadki, jednorazowy przypadek.
    if (onboarding) return <Onboarding />
    if (isOnboardingParam) {
      // Jawne wejście do kreatora (?onboarding, np. ze strony ?start). Na zajętej
      // instancji kreator działa w trybie PODGLĄDU (demo) — kroki bez zapisu.
      if (onboarding === null) return <LazyFallback label="Sprawdzanie konfiguracji lokalu" />
      return <Onboarding demo />
    }
    if (isStart) return <Start />                 // ?start → kreator (świeża instancja) albo jasny rozjazd
    if (isLogin) return <Landing />               // ?login → ekran logowania (z landingu „Zaloguj")
    if (isWorkstation) return <Landing />          // niezarejestrowane stanowisko → logowanie admina do konfiguracji
    return <Produkt />                            // publiczny landing sprzedażowy (domyślny widok gościa)
  }
  if (user.rola === 'admin') return <Dashboard />
  if (user.rola === 'szef') return <SzefView key={`szef:${workstationVersion || 0}`} />
  if (user.rola === 'szef_kuchni') return <SzefKuchniView />
  return <EmployeeArea />   // employee (obsługa) i kuchnia — kuchnia ma ukrytą Dyspozycyjność
}

function AppContent() {
  // Aplikacja NATYWNA bez zapisanego adresu instancji → najpierw ekran „adres instancji".
  // (Na webie jestNatywna()=false i getApiBase()='' → ten warunek nigdy nie zachodzi.)
  const [maBaze, setMaBaze] = useState(!!getApiBase())
  if (jestNatywna() && !maBaze) {
    return (
      <MotionConfig reducedMotion="user">
        <WyborInstancji onGotowe={() => setMaBaze(true)} />
      </MotionConfig>
    )
  }

  // Dokumenty prawne — publiczne, statyczne, bez logowania (linkowane ze stopki i kreatora).
  if (isPolityka || isRegulamin) {
    return (
      <MotionConfig reducedMotion="user">
        <Dokument ktory={isRegulamin ? 'regulamin' : 'polityka'} />
      </MotionConfig>
    )
  }
  // Strona produktu (marketing/cennik) — statyczna, bez logowania i bez kontekstów instancji.
  if (isProdukt) {
    return (
      <MotionConfig reducedMotion="user">
        <Produkt />
      </MotionConfig>
    )
  }
  // Rejestracja pracownika z linku-zaproszenia — publiczna, poza AuthProvider
  // (osoba nie ma jeszcze konta; po rejestracji pełne przeładowanie do panelu).
  if (zaproszenieToken) {
    return (
      <MotionConfig reducedMotion="user">
        <BrandingProvider>
          <Zaproszenie token={zaproszenieToken} />
        </BrandingProvider>
      </MotionConfig>
    )
  }
  if (isWidget) {
    return (
      <MotionConfig reducedMotion="user">
        <BrandingProvider>
          <ToastProvider>
            <RezerwacjaWidget />
          </ToastProvider>
        </BrandingProvider>
      </MotionConfig>
    )
  }
  if (isPortalImprezy) {
    return (
      <MotionConfig reducedMotion="user">
        <BrandingProvider>
          <ToastProvider>
            <PortalImprezy />
          </ToastProvider>
        </BrandingProvider>
      </MotionConfig>
    )
  }
  return (
    <MotionConfig reducedMotion="user">
      <BrandingProvider>
        <AuthProvider>
          <ToastProvider>
            <DataProvider>
              <Routed />
            </DataProvider>
          </ToastProvider>
        </AuthProvider>
      </BrandingProvider>
    </MotionConfig>
  )
}

export default function App() {
  return (
    <LazyErrorBoundary fullPage>
      <Suspense fallback={<LazyFallback label="Ładowanie aplikacji" />}>
        <AppContent />
      </Suspense>
    </LazyErrorBoundary>
  )
}
