import { Spinner } from './Spinner'

// Przycisk systemu „Cicha scena" — spokojne, natywne warianty bez poświat i gradientów.
const VARIANTS = {
  // Główne CTA: neutralna jasna pigułka na ciemnym tle (jedna nadrzędna akcja na widok)
  primary: 'bg-cream text-bg hover:bg-white',
  // Akcent szałwiowy — wyróżnione, brandowe akcje (rzadko)
  accent: 'bg-mint text-bg hover:brightness-105',
  success: 'bg-success text-bg hover:brightness-105',
  danger: 'bg-danger text-white hover:brightness-110',
  // Subtelny, obrysowany — akcje drugorzędne (szkło: rozjaśnienie obrysu na hover)
  ghost: 'border border-white/[0.10] bg-white/[0.04] text-ink hover:border-white/[0.16] hover:bg-white/[0.08]',
  subtle: 'bg-white/[0.04] text-muted hover:text-ink hover:bg-white/[0.08]',
}

const SIZES = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-5 py-2.5 text-sm',
  lg: 'px-7 py-3 text-base',
}

export function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  className = '',
  children,
  disabled = false,
  loading = false,
  loadingLabel,
  'aria-label': ariaLabel,
  'aria-busy': ariaBusy,
  ...props
}) {
  return (
    <button
      type={type}
      {...props}
      aria-label={loading && loadingLabel ? loadingLabel : ariaLabel}
      aria-busy={loading ? true : ariaBusy}
      disabled={disabled || loading}
      className={`inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-xl font-semibold tracking-tight
        transition duration-150 ease-snap active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50
        ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      <span className="grid items-center justify-items-center">
        <span
          className={`col-start-1 row-start-1 inline-flex items-center gap-2 ${loading ? 'opacity-0' : ''}`}
          aria-hidden={loading && loadingLabel ? true : undefined}
        >
          {children}
        </span>
        <span
          className={`col-start-1 row-start-1 inline-flex items-center gap-2 ${loading ? '' : 'invisible'}`}
          aria-hidden={!loading || !loadingLabel ? true : undefined}
        >
          <Spinner className="h-4 w-4 shrink-0 motion-reduce:animate-none" />
          {loadingLabel ? <span>{loadingLabel}</span> : null}
        </span>
      </span>
    </button>
  )
}
