import logoUrl from '../assets/logo.svg'

// Logo aplikacji renderowane przez maskę CSS. Plik SVG jest jednokolorowy
// (czarny), więc maska pozwala nadać mu dowolny kolor motywu:
//   variant="ink"      -> jasny logotyp na ciemnym tle
//   variant="bg"       -> ciemny logotyp na jasnym/gradientowym kaflu
//   variant="gradient" -> logotyp w gradiencie akcentowym
// Rozmiar ustawiamy klasą wysokości (np. h-6); szerokość wynika z proporcji.
const VARIANT_BG = {
  ink: 'bg-ink',
  bg: 'bg-bg',
  gradient: 'bg-accent-gradient',
}

export function Logo({ className = 'h-5', variant = 'ink' }) {
  return (
    <span
      role="img"
      aria-label="Logo Grafik Pracy"
      className={`inline-block aspect-[780/545] ${VARIANT_BG[variant] || VARIANT_BG.ink} ${className}`}
      style={{
        WebkitMaskImage: `url(${logoUrl})`,
        maskImage: `url(${logoUrl})`,
        WebkitMaskRepeat: 'no-repeat',
        maskRepeat: 'no-repeat',
        WebkitMaskPosition: 'center',
        maskPosition: 'center',
        WebkitMaskSize: 'contain',
        maskSize: 'contain',
      }}
    />
  )
}
