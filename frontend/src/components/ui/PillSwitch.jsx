import { BOUNCE } from '../../lib/motion'

// Segmented control (jak natywny iOS/macOS) — CZYSTY CSS (kompozytor → na ProMotion/iPhone
// może chodzić w 120 Hz). Wskaźnik przesuwa się pod aktywną opcją przez `transform: translateX`
// z krzywą szuflady iOS (bez odbicia). Press = scale(0.97).
//
// options: [{ value, label, activeBg, activeText, badge }]
//   activeBg   – tło aktywnego segmentu (domyślnie uniesiona powierzchnia). Solid kolory
//                (np. bg-success/bg-danger) ładnie się przenikają przy zmianie stanu.
//   activeText – kolor tekstu na aktywnym segmencie (domyślnie text-ink)
export function PillSwitch({ options, value, onChange, className = '' }) {
  const activeIndex = Math.max(0, options.findIndex((o) => o.value === value))
  const active = options[activeIndex] || options[0]
  return (
    <div className={`relative flex rounded-2xl border border-line bg-white/[0.03] p-1.5 ${className}`}>
      {/* Wskaźnik — sam transform/opacity (GPU), bez JS. Spokojny glide, zero overshootu. */}
      <span
        aria-hidden
        className={`pointer-events-none absolute inset-y-1.5 left-1.5 rounded-xl shadow-cta will-change-transform ${active.activeBg || 'bg-surface-2'}`}
        style={{
          width: `calc((100% - 0.75rem) / ${options.length})`,
          transform: `translateX(${activeIndex * 100}%)`,
          transition: `transform 280ms ${BOUNCE}, background-color 200ms ease`,
        }}
      />
      {options.map((opt) => {
        const isActive = opt.value === value
        return (
          <button
            key={String(opt.value)}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`relative z-10 flex-1 rounded-xl px-3 py-2 text-sm font-semibold transition-[color,transform] duration-150 ease-snap active:scale-[0.97] ${
              isActive ? opt.activeText || 'text-ink' : 'text-muted hover:text-ink'
            }`}
            style={{ WebkitTapHighlightColor: 'transparent' }}
          >
            {opt.label}
            {opt.badge && <span className="absolute right-2 top-1.5 h-2.5 w-2.5 rounded-full bg-coral ring-2 ring-bg" />}
          </button>
        )
      })}
    </div>
  )
}
