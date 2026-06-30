import { useBranding } from '../context/BrandingContext'

// Neutralny, produktowy znak (kalendarz/grafik) w gradiencie akcentowym marki.
// Bez zewnętrznych plików — czysty SVG inline. Gdy lokal ma własne logo (branding.logo_url),
// pokazujemy je zamiast znaku domyślnego. `variant` zachowany dla zgodności API (znak jest
// samokolorujący gradientem, więc wygląda dobrze na ciemnym UI niezależnie od wariantu).

// Sam znak SVG (gradient akcentowy). `idSuffix` unika kolizji id gradientu przy wielu instancjach.
function Mark({ idSuffix = '', title = '' }) {
  const gid = `brandgrad${idSuffix}`
  return (
    <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-full w-full"
         role="img" aria-label={title || undefined} aria-hidden={title ? undefined : true}>
      <defs>
        <linearGradient id={gid} x1="4" y1="4" x2="44" y2="44" gradientUnits="userSpaceOnUse">
          <stop stopColor="#F4E2A0" />
          <stop offset="0.5" stopColor="#A7D7C5" />
          <stop offset="1" stopColor="#F2B8CB" />
        </linearGradient>
      </defs>
      {/* korpus kalendarza */}
      <rect x="5.5" y="10" width="37" height="31.5" rx="8" stroke={`url(#${gid})`} strokeWidth="3" />
      {/* uchwyty u góry */}
      <line x1="15" y1="6" x2="15" y2="13" stroke={`url(#${gid})`} strokeWidth="3" strokeLinecap="round" />
      <line x1="33" y1="6" x2="33" y2="13" stroke={`url(#${gid})`} strokeWidth="3" strokeLinecap="round" />
      {/* komórki grafiku — dwie wypełnione (zaplanowane sloty), dwie przygaszone */}
      <rect x="12" y="20.5" width="9" height="7" rx="2" fill={`url(#${gid})`} />
      <rect x="27" y="20.5" width="9" height="7" rx="2" fill={`url(#${gid})`} opacity="0.32" />
      <rect x="12" y="31" width="9" height="7" rx="2" fill={`url(#${gid})`} opacity="0.32" />
      <rect x="27" y="31" width="9" height="7" rx="2" fill={`url(#${gid})`} />
    </svg>
  )
}

// Sam znak — do małych kafli (nagłówki, logowanie). Aspekt 1:1.
export function Logo({ className = 'h-5', variant = 'ink' }) {
  const { logo_url, nazwa_lokalu } = useBranding()
  if (logo_url) {
    return <img src={logo_url} alt={nazwa_lokalu} className={`inline-block w-auto object-contain ${className}`} />
  }
  return (
    <span className={`inline-block aspect-square ${className}`}>
      <Mark idSuffix="-s" title={nazwa_lokalu} />
    </span>
  )
}

// „Animowany" znak na ekranie głównym — neutralny mark z delikatnym unoszeniem (bez wiatraka).
export function AnimatedLogo({ className = 'h-24', spin = true }) {
  const { logo_url, nazwa_lokalu } = useBranding()
  if (logo_url) {
    return <img src={logo_url} alt={nazwa_lokalu} className={`inline-block w-auto object-contain ${className}`} />
  }
  return (
    <span className={`inline-block aspect-square ${spin ? 'animate-float motion-reduce:animate-none' : ''} ${className}`}>
      <Mark idSuffix="-a" title={nazwa_lokalu} />
    </span>
  )
}

// Pełny logotyp: znak + nazwa lokalu (z brandingu). Custom logo z URL nadpisuje całość.
export function LogoFull({ className = 'h-12', variant = 'ink' }) {
  const { logo_url, nazwa_lokalu } = useBranding()
  if (logo_url) {
    return <img src={logo_url} alt={nazwa_lokalu} className={`inline-block w-auto object-contain ${className}`} />
  }
  return (
    <span className={`inline-flex items-center gap-3 ${className}`}>
      <span className="inline-block aspect-square h-full"><Mark idSuffix="-f" title={nazwa_lokalu} /></span>
      <span className="font-display font-bold text-ink leading-none" style={{ fontSize: '0.5em' }}>{nazwa_lokalu}</span>
    </span>
  )
}
