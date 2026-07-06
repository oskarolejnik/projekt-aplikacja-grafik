// Konfiguracja testów (Vitest). Uruchamiana per plik testowy w jego środowisku.
// jsdom NIE implementuje window.matchMedia, a GSAP ScrollTrigger.register tego wymaga
// (import landing/motionPro.js woła registerPlugin na starcie). Dokładamy bezpieczny stub.
// W środowisku 'node' (brak window) warunek pomija polyfill.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })
}
