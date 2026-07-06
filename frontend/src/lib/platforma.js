// Wykrywanie środowiska natywnego (Capacitor). Bez twardej zależności od @capacitor/core —
// gdy apka działa natywnie, Capacitor wstrzykuje globalny obiekt window.Capacitor.
// W przeglądarce / PWA zwraca false (zero wpływu na web).
export const jestNatywna = () =>
  !!(typeof window !== 'undefined' && window.Capacitor
     && typeof window.Capacitor.isNativePlatform === 'function'
     && window.Capacitor.isNativePlatform())
