// Wspólne tokeny ruchu — system „Cicha scena" (Apple-like): ruch komunikuje stan,
// nigdy nie dekoruje. Sprężyny bez odbić — gładkie osiadanie (critically damped),
// czasy 150–300 ms. Eksporty zachowują historyczne nazwy (zero churnu w komponentach).
export const SPRING = { type: 'spring', bounce: 0, duration: 0.4 }

// Sztywniejsza sprężyna do przejść treści (szybsze osiadanie).
export const SPRING_SNAPPY = { type: 'spring', bounce: 0, duration: 0.3 }

// Wskaźniki „podróżujące" (Pill Switcher, shared layout) — spokojny glide, bez overshootu.
export const SPRING_PILL = { type: 'spring', bounce: 0.05, duration: 0.35 }

// Reflow/zwijanie layoutu (karty „podjeżdżają", pola się zwijają).
export const SPRING_LAYOUT = { type: 'spring', bounce: 0.05, duration: 0.35 }

// CSS easing dla animacji kompozytora (transform) — krzywa szuflady iOS, bez odbicia.
// Nazwa historyczna (dawniej easeOutBack) — wartość celowo już nie „strzela".
export const BOUNCE = 'cubic-bezier(0.32, 0.72, 0, 1)'
