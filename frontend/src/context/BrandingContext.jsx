import { createContext, useContext, useState, useEffect } from 'react'
import { api } from '../lib/api'

// Branding lokalu (white-label). Pobierany z publicznego /api/lokal/branding przy starcie.
// Wartości domyślne = neutralna marka produktu (gdy backend nie zwróci konfiguracji).
const DOMYSLNY = { nazwa_lokalu: 'Grafik Pracy', logo_url: null, kolor_primary: null }

const BrandingContext = createContext(DOMYSLNY)

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DOMYSLNY)

  useEffect(() => {
    let anulowane = false
    api('/lokal/branding')
      .then((b) => {
        if (!anulowane && b && b.nazwa_lokalu) setBranding({ ...DOMYSLNY, ...b })
      })
      .catch(() => {}) // brak/niedostępny branding → zostają wartości domyślne
    return () => { anulowane = true }
  }, [])

  // Efekty uboczne marki: tytuł karty + zmienna CSS koloru (do wykorzystania w stylach).
  useEffect(() => {
    if (branding.nazwa_lokalu) document.title = branding.nazwa_lokalu
    if (branding.kolor_primary) {
      document.documentElement.style.setProperty('--brand-primary', branding.kolor_primary)
    }
  }, [branding])

  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>
}

export const useBranding = () => useContext(BrandingContext)
