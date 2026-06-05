import { MotionConfig } from 'framer-motion'
import { AuthProvider, useAuth } from './context/AuthContext'
import { DataProvider } from './context/DataContext'
import { ToastProvider } from './components/ui/Toast'
import { Spinner } from './components/ui/Spinner'
import Landing from './pages/Landing'
import Dashboard from './Dashboard'
import EmployeeArea from './pages/EmployeeArea'

// Routing wg stanu zalogowania i roli:
//   brak użytkownika → ekran startowy (z logowaniem)
//   admin            → pełny panel zarządzania
//   employee         → samoobsługa dyspozycyjności
function Routed() {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center bg-bg">
        <Spinner className="h-7 w-7 text-muted" />
      </div>
    )
  }
  if (!user) return <Landing />
  if (user.rola === 'admin') return <Dashboard />
  return <EmployeeArea />
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <AuthProvider>
        <ToastProvider>
          <DataProvider>
            <Routed />
          </DataProvider>
        </ToastProvider>
      </AuthProvider>
    </MotionConfig>
  )
}
