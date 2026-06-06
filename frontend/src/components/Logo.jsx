import markUrl from '../assets/logo-mark.png'
import fullUrl from '../assets/logo-rajcula.png'
import buildingSvg from '../assets/logo-building.svg'
import bladesSvg from '../assets/logo-blades.svg'

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
  // Gradient akcentowy, który delikatnie „płynie" (kołysanie kolorów) — ekran logowania.
  'gradient-flow': 'bg-accent-flow bg-[length:250%_100%] animate-gradient-flow',
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

// Animowane logo: zabudowanie stoi nieruchomo, a skrzydła wiatraka obracają się płasko
// (360°) wokół piasty (różowy okrąg z pliku autora → oś 70.77%/40.07% kadru, na wieży).
// Skrzydła są celowo proporcjonalne/symetryczne, więc płaski obrót wygląda naturalnie bez
// pochylenia perspektywicznego. Obie warstwy to maski CSS (SVG z konkretnymi wymiarami +
// mask-size 100% — inaczej maska znikała na Safari i kręcił się sam gradientowy prostokąt)
// w „płynącym" gradiencie akcentowym. Mocny cień pod skrzydłami odcina je od budynku.
// Dwie osobne warstwy = przestrzeń za skrzydłami pozostaje nienaruszona podczas ruchu.
const FLOW = 'bg-accent-flow bg-[length:250%_100%] animate-gradient-flow'
// Maska rozciągnięta 1:1 do kafla (kafel ma proporcje SVG) — pewniejsze na Safari niż „contain".
const maskFill = (url) => ({ ...maskStyle(url), WebkitMaskSize: '100% 100%', maskSize: '100% 100%' })
export function AnimatedLogo({ className = 'h-24', spin = true }) {
  return (
    <span role="img" aria-label="Rajcula" className={`relative inline-block aspect-[756/569] ${className}`}>
      {/* budynek — statyczny */}
      <span className={`absolute inset-0 ${FLOW}`} style={maskFill(buildingSvg)} />
      {/* skrzydła — płaski obrót 360° wokół piasty + mocny cień odcinający od budynku */}
      <span
        className={`absolute inset-0 ${spin ? 'animate-windmill motion-reduce:animate-none' : ''}`}
        style={{
          transformOrigin: '70.77% 40.07%',
          filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.8)) drop-shadow(0 0 2px rgba(0,0,0,0.6))',
          willChange: 'transform',
        }}
      >
        <span className={`absolute inset-0 ${FLOW}`} style={maskFill(bladesSvg)} />
      </span>
    </span>
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
