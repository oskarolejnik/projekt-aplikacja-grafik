import { createContext, useContext, useState, useCallback, useMemo } from 'react'
import { api } from '../lib/api'
import { generujOpcjeTygodni } from '../lib/weeks'

// Współdzielony stan: słowniki (stanowiska, pracownicy) oraz wybrany tydzień.
// Zastępuje globalny obiekt STATE z poprzedniej aplikacji.
const DataContext = createContext(null)

export function DataProvider({ children }) {
  const { opcje, domyslny, biezacy, przyszly } = useMemo(() => generujOpcjeTygodni(), [])
  const [week, setWeek] = useState(domyslny)
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
