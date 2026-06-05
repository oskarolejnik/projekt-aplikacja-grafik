// Wspólne tokeny ruchu (styl Emila Kowalskiego / Apple). Fizyka sprężyny dla
// wskaźników „podróżujących" (Pill Switcher, shared layout) — naturalny, organiczny ruch.
// API perceptualne (duration+bounce) — Emil poleca je jako czytelniejsze niż stiffness/damping.
// Niski bounce + dłuższe osiadanie = gładki, płynny „glide" zamiast szarpniętego snapu.
export const SPRING = { type: 'spring', bounce: 0.18, duration: 0.55 }

// Sztywniejsza sprężyna do przejść treści (szybsze osiadanie, wciąż miękkie).
export const SPRING_SNAPPY = { type: 'spring', bounce: 0.12, duration: 0.4 }

// Pigułki (Pill Switcher) — wyraźniejszy, „apple'owy" bounce: gładki overshoot i miękkie osiadanie.
export const SPRING_PILL = { type: 'spring', bounce: 0.34, duration: 0.6 }

// Reflow/zwijanie layoutu (karty „podjeżdżają", pola się zwijają) — spójne ze sprężyną pigułek.
export const SPRING_LAYOUT = { type: 'spring', bounce: 0.2, duration: 0.5 }

// CSS easing z „overshootem" (easeOutBack) — bounce dla animacji kompozytora (transform),
// które na iOS/ProMotion mogą iść w 120 Hz (w przeciwieństwie do rAF Framera ~60 Hz).
export const BOUNCE = 'cubic-bezier(0.34, 1.56, 0.64, 1)'
