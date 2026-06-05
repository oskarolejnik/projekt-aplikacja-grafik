import { motion } from 'framer-motion'
import { SPRING_PILL } from '../../lib/motion'

// Pill Switcher (styl Apple / Emil Kowalski): wskaźnik aktywnego stanu „podróżuje"
// pod tekstem (Framer `layoutId` = shared element + fizyka sprężyny), zamiast
// pojawiać się nagle. Press = scale(0.95) realizowany CSS-em (`active:`), żeby nie
// kolidować z pomiarem layoutu przez Framer Motion.
//
// options: [{ value, label, activeBg, activeText, badge }]
//   activeBg   – tło aktywnej pigułki (domyślnie gradient akcentowy)
//   activeText – kolor tekstu na aktywnej pigułce (domyślnie text-bg)
export function PillSwitch({ options, value, onChange, layoutId, className = '' }) {
  return (
    <div className={`relative flex gap-1 rounded-2xl border border-line bg-white/[0.03] p-1.5 ${className}`}>
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={String(opt.value)}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`relative flex-1 rounded-xl px-3 py-2 text-sm font-bold transition-[color,transform] duration-150 ease-snap active:scale-[0.95] ${
              active ? '' : 'text-muted hover:text-ink'
            }`}
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            {active && (
              <motion.span
                layoutId={layoutId}
                transition={SPRING_PILL}
                className={`absolute inset-0 rounded-xl ${opt.activeBg || 'bg-accent-gradient'}`}
              />
            )}
            <span className={`relative z-10 ${active ? opt.activeText || 'text-bg' : ''}`}>{opt.label}</span>
            {opt.badge && <span className="absolute right-2 top-1.5 z-10 h-2.5 w-2.5 rounded-full bg-coral ring-2 ring-bg" />}
          </button>
        )
      })}
    </div>
  )
}
