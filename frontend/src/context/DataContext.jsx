import { createContext, useContext, useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { generujOpcjeTygodni } from '../lib/weeks'
import { useBranding } from './BrandingContext'

// Współdzielony stan: słowniki (stanowiska, pracownicy) oraz wybrany tydzień.
// Zastępuje globalny obiekt STATE z poprzedniej aplikacji.
const DataContext = createContext(null)

export function DataProvider({ children }) {
  // Początek tygodnia grafiku z konfiguracji lokalu (publiczny branding — dostępny każdej
  // roli). Zanim branding dojedzie, generator działa na domyślnej środzie; po zmianie dnia
  // opcje są przeliczane, a wybrany tydzień wraca na bieżący (stary zakres traci sens).
  const { poczatek_tygodnia } = useBranding()
  const { opcje, domyslny, biezacy, przyszly } = useMemo(
    () => generujOpcjeTygodni(poczatek_tygodnia),
    [poczatek_tygodnia],
  )
  const [week, setWeek] = useState(domyslny)
  const pierwszyRender = useRef(true)
  useEffect(() => {
    if (pierwszyRender.current) { pierwszyRender.current = false; return }
    setWeek(domyslny)
  }, [domyslny])
  const [stanowiska, setStanowiska] = useState([])
  const [pracownicy, setPracownicy] = useState([])

  const reloadDicts = useCallback(async () => {
    const [s, p] = await Promise.all([api('/stanowiska'), api('/pracownicy')])
    setStanowiska(s)
    setPracownicy(p)
    return { stanowiska: s, pracownicy: p }
  }, [])

  const value = {
    weeks: opcje,
    week,
    setWeek,
    biezacy,
    przyszly,
    weekRange: () => week.split('|'),
    stanowiska,
    pracownicy,
    setStanowiska,
    setPracownicy,
    reloadDicts,
  }

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>
}

export const useData = () => useContext(DataContext)
