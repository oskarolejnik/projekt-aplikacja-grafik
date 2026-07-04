import { useState, useEffect } from 'react'
import { MotionConfig } from 'framer-motion'
import { AuthProvider, useAuth } from './context/AuthContext'
import { BrandingProvider } from './context/BrandingContext'
import { DataProvider } from './context/DataContext'
import { ToastProvider } from './components/ui/Toast'
import { Spinner } from './components/ui/Spinner'
import Landing from './pages/Landing'
import Dashboard from './Dashboard'
import EmployeeArea from './pages/EmployeeArea'
import SzefView from './pages/SzefView'
import SzefKuchniView from './pages/SzefKuchniView'
import RezerwacjaWidget from './pages/RezerwacjaWidget'
import PortalImprezy from './pages/PortalImprezy'
import Onboarding from './pages/Onboarding'
import Start from './pages/Start'
import Produkt from './pages/Produkt'
import Zaproszenie from './pages/Zaproszenie'
import { api } from './lib/api'

// Publiczne „trasy" wykrywane po query param (bez logowania, poza AuthProvider):
//   ?rezerwuj → widget rezerwacji gościa,  ?produkt → strona produktu/cennik (marketing),
//   ?impreza=TOKEN → portal klienta imprezy (para młoda / organizator).
const _params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : new URLSearchParams()
const isWidget = _params.has('rezerwuj')
const isPortalImprezy = _params.has('impreza')
const isProdukt = _params.has('produkt')
const isLogin = _params.has('login')   // ?login → ekran logowania (landing marketingowy prowadzi tu z „Zaloguj")
const isStart = _params.has('start')   // ?start → kreator lokalu (świeża instancja) lub rozjazd „co dalej"
const isOnboardingParam = _params.has('onboarding')   // ?onboarding → kreator zawsze (na zajętej instancji: podgląd demo)
const zaproszenieToken = _params.get('zaproszenie')   // ?zaproszenie=TOKEN → rejestracja pracownika z linku

// Routing wg stanu zalogowania i roli:
//   brak użytkownika → ekran startowy (z logowaniem)
//   admin            → pełny panel zarządzania
//   employee         → samoobsługa dyspozycyjności
function Routed() {
  const { user, loading } = useAuth()
  // Dla niezalogowanego sprawdź, czy instancja jest świeża (0 użytkowników) → kreator zamiast logowania.
  const [onboarding, setOnboarding] = useState(null)   // null = sprawdzam, true/false
  useEffect(() => {
    if (loading || user) return
    api('/onboarding/status').then((s) => setOnboarding(!!s.potrzebny)).catch(() => setOnboarding(false))
  }, [loading, user])

  const spinner = (
    <div className="grid min-h-dvh place-items-center bg-bg">
      <Spinner className="h-7 w-7 text-muted" />
    </div>
  )
  if (loading) return spinner
  if (!user) {
    // Nie blokujemy publicznej strony sprzedażowej spinnerem na czas /onboarding/status —
    // domyślnie (status jeszcze null) renderujemy landing OD RAZU. Kreator pokazujemy dopiero,
    // gdy status potwierdzi świeżą instancję (potrzebny=true) — rzadki, jednorazowy przypadek.
    if (onboarding) return <Onboarding />
    if (isOnboardingParam) {
      // Jawne wejście do kreatora (?onboarding, np. ze strony ?start). Na zajętej
      // instancji kreator działa w trybie PODGLĄDU (demo) — kroki bez zapisu.
      if (onboarding === null) return spinner
      return <Onboarding demo />
    }
    if (isStart) return <Start />                 // ?start → kreator (świeża instancja) albo jasny rozjazd
    if (isLogin) return <Landing />               // ?login → ekran logowania (z landingu „Zaloguj")
    return <Produkt />                            // publiczny landing sprzedażowy (domyślny widok gościa)
  }
  if (user.rola === 'admin') return <Dashboard />
  if (user.rola === 'szef') return <SzefView />
  if (user.rola === 'szef_kuchni') return <SzefKuchniView />
  return <EmployeeArea />   // employee (obsługa) i kuchnia — kuchnia ma ukrytą Dyspozycyjność
}

export default function App() {
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
