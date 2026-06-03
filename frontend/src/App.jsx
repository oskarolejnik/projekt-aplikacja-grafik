import { useState } from 'react'
import { DataProvider } from './context/DataContext'
import { ToastProvider } from './components/ui/Toast'
import Landing from './pages/Landing'
import Dashboard from './Dashboard'

// Ekran startowy (Landing) działa jako markowy „splash” — wejście prowadzi do
// panelu. Stan trzymany lokalnie; brak routingu po URL (upraszcza serwowanie SPA).
export default function App() {
  const [entered, setEntered] = useState(false)
  return (
    <DataProvider>
      <ToastProvider>
        {entered ? <Dashboard onExit={() => setEntered(false)} /> : <Landing onEnter={() => setEntered(true)} />}
      </ToastProvider>
    </DataProvider>
  )
}
