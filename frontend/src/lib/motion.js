// Wspólne tokeny ruchu (styl Emila Kowalskiego / Apple). Fizyka sprężyny dla
// wskaźników „podróżujących" (Pill Switcher, shared layout) — naturalny, organiczny ruch.
// API perceptualne (duration+bounce) — Emil poleca je jako czytelniejsze niż stiffness/damping.
// Niski bounce + dłuższe osiadanie = gładki, płynny „glide" zamiast szarpniętego snapu.
export const SPRING = { type: 'spring', bounce: 0.18, duration: 0.55 }

// Sztywniejsza sprężyna do przejść treści (szybsze osiadanie, wciąż miękkie).
export const SPRING_SNAPPY = { type: 'spring', bounce: 0.12, duration: 0.4 }
