// Wspólne tokeny ruchu (styl Emila Kowalskiego / Apple). Fizyka sprężyny dla
// wskaźników „podróżujących" (Pill Switcher, shared layout) — naturalny, organiczny ruch.
export const SPRING = { type: 'spring', stiffness: 200, damping: 25 }

// Sztywniejsza sprężyna do przejść treści (szybsze osiadanie, wciąż miękkie).
export const SPRING_SNAPPY = { type: 'spring', stiffness: 300, damping: 30 }
