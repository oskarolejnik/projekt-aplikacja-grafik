import markUrl from '../assets/logo-mark.png'
import fullUrl from '../assets/logo-rajcula.png'

// Logo Rajcula renderowane maską CSS (źródło jest jednokolorowe — maska pozwala
// nadać dowolny kolor motywu):
//   variant="ink"      -> jasny logotyp na ciemnym tle
//   variant="bg"       -> ciemny logotyp na jasnym/gradientowym kaflu
//   variant="gradient" -> logotyp w gradiencie akcentowym
// Rozmiar ustawiamy klasą wysokości (np. h-6); szerokość wynika z proporcji.
const VARIANT_BG = {
  ink: 'bg-ink',
  bg: 'bg-bg',
  gradient: 'bg-accent-gradient',
}

const maskStyle = (url) => ({
  WebkitMaskImage: `url(${url})`,
  maskImage: `url(${url})`,
  WebkitMaskRepeat: 'no-repeat',
  maskRepeat: 'no-repeat',
  WebkitMaskPosition: 'center',
  maskPosition: 'center',
  WebkitMaskSize: 'contain',
  maskSize: 'contain',
})

// Sam znak (wiatrak + zabudowanie) — do małych kafli (nagłówki, logowanie).
export function Logo({ className = 'h-5', variant = 'ink' }) {
  return (
    <span
      role="img"
      aria-label="Rajcula"
      className={`inline-block aspect-[758/539] ${VARIANT_BG[variant] || VARIANT_BG.ink} ${className}`}
      style={maskStyle(markUrl)}
    />
  )
}

// Pełny logotyp (znak + napis „Rajcula") — np. ekran główny.
export function LogoFull({ className = 'h-24', variant = 'ink' }) {
  return (
    <span
      role="img"
      aria-label="Rajcula"
      className={`inline-block aspect-[2400/1681] ${VARIANT_BG[variant] || VARIANT_BG.ink} ${className}`}
      style={maskStyle(fullUrl)}
    />
  )
}
