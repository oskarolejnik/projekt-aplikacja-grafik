import { useBranding } from '../context/BrandingContext'

// Neutralny, produktowy znak (kalendarz/grafik) w gradiencie akcentowym marki.
// Bez zewnętrznych plików — czysty SVG inline. Gdy lokal ma własne logo (branding.logo_url),
// pokazujemy je zamiast znaku domyślnego. `variant` zachowany dla zgodności API (znak jest
// samokolorujący gradientem, więc wygląda dobrze na ciemnym UI niezależnie od wariantu).

// Znak marki Lokalo: gradientowy kafel (app-tile) z monogramem „L" i akcentem.
// `idSuffix` unika kolizji id gradientu przy wielu instancjach.
function Mark({ idSuffix = '', title = '' }) {
  const gid = `brandgrad${idSuffix}`
  return (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-full w-full"
         role="img" aria-label={title || undefined} aria-hidden={title ? undefined : true}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop stopColor="#A7D7C5" />
          <stop offset="0.52" stopColor="#F4E2A0" />
          <stop offset="1" stopColor="#F2A2A2" />
        </linearGradient>
      </defs>
      {/* kafel marki */}
      <rect x="0" y="0" width="64" height="64" rx="15" fill={`url(#${gid})`} />
      {/* monogram L */}
      <path d="M21 16 H28.5 V41 H45 V48.5 H21 Z" fill="#1C1C1E" />
      {/* akcent (miejsce / punkt) */}
      <circle cx="43.5" cy="21.5" r="4.6" fill="#1C1C1E" />
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

// Duży znak na ekranie głównym — statyczny (Cicha scena: ruch komunikuje stan, nie dekoruje).
// Prop `spin` zachowany dla zgodności API, celowo ignorowany.
export function AnimatedLogo({ className = 'h-24', spin = true }) {
  const { logo_url, nazwa_lokalu } = useBranding()
  if (logo_url) {
    return <img src={logo_url} alt={nazwa_lokalu} className={`inline-block w-auto object-contain ${className}`} />
  }
  return (
    <span className={`inline-block aspect-square ${className}`}>
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
