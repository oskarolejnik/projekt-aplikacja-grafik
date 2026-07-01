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
import Onboarding from './pages/Onboarding'
import { api } from './lib/api'

// Publiczny widget rezerwacji (gość, bez logowania) — osobna „trasa" wykrywana po ?rezerwuj.
// Działa POZA AuthProvider (nie wymaga tokenu); branding z publicznego /api/lokal/branding.
const isWidget = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('rezerwuj')

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
    if (onboarding === null) return spinner       // czekamy na status onboardingu
    if (onboarding) return <Onboarding />
    return <Landing />
  }
  if (user.rola === 'admin') return <Dashboard />
  if (user.rola === 'szef') return <SzefView />
  if (user.rola === 'szef_kuchni') return <SzefKuchniView />
  return <EmployeeArea />   // employee (obsługa) i kuchnia — kuchnia ma ukrytą Dyspozycyjność
}

export default function App() {
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
