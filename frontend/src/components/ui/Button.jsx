// Przycisk w stylu "Creativity" — pigułki z miękkim cieniem i naciśnięciem (scale).
const VARIANTS = {
  // Główne CTA: kremowa pigułka na ciemnym tle (jak "TICKETS" z referencji)
  primary: 'bg-cream text-bg hover:shadow-cta hover:brightness-[1.03]',
  // Akcent gradientowy (rzadziej, dla wyróżnionych akcji)
  accent: 'bg-accent-gradient text-bg hover:brightness-105',
  success: 'bg-success text-bg hover:brightness-105',
  danger: 'bg-danger text-white hover:brightness-110',
  // Subtelny, obrysowany — akcje drugorzędne
  ghost: 'border border-line bg-white/[0.04] text-ink hover:bg-white/[0.09]',
  subtle: 'bg-white/[0.04] text-muted hover:text-ink hover:bg-white/[0.09]',
}

const SIZES = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-5 py-2.5 text-sm',
  lg: 'px-7 py-3 text-base',
}

export function Button({ variant = 'primary', size = 'md', className = '', children, ...props }) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-semibold tracking-tight
        transition duration-150 ease-snap active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50
        ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {children}
    </button>
  )
}
