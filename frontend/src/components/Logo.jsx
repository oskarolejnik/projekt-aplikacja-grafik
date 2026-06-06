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

// Animowane logo: zabudowanie stoi nieruchomo, a 4 skrzydła wiatraka obracają się
// wokół piasty (różowy okrąg z pliku autora → oś 67.87%/44.32% kadru, na wieży).
// Obrót w płaszczyźnie pochylonej wokół osi PIONOWEj (rotateY = --wtilt, ujemny →
// lewa strona się oddala/zmniejsza) zgodnej z perspektywą wieży, z lekką głębią
// (perspective). Obie warstwy to maski CSS w „płynącym" gradiencie akcentowym. Lekki
// cień pod skrzydłami odcina je od tła. Dwie osobne warstwy = przestrzeń za skrzydłami
// pozostaje nienaruszona podczas ruchu.
const FLOW = 'bg-accent-flow bg-[length:250%_100%] animate-gradient-flow'
export function AnimatedLogo({ className = 'h-24', spin = true }) {
  return (
    <span
      role="img"
      aria-label="Rajcula"
      className={`relative inline-block aspect-[803/607] ${className}`}
      style={{ perspective: '1200px' }}
    >
      {/* budynek — statyczny */}
      <span className={`absolute inset-0 ${FLOW}`} style={maskStyle(buildingSvg)} />
      {/* skrzydła — obrót wokół piasty w pochylonej płaszczyźnie + cień odcinający od tła.
          Pochylenie i obrót są ROZDZIELONE na dwie właściwości (inaczej mieszanie rotateY+rotate
          w jednej animacji psuje interpolację → brak ruchu):
          • rotate: y -15deg  — statyczne pochylenie wokół osi pionowej (lewa strona się oddala),
          • transform: rotate(0→360) (animate-windmill) — obrót skrzydeł.
          Kolejność CSS (transform przed rotate) sprawia, że obrót dzieje się w pochylonej płaszczyźnie. */}
      <span
        className={`absolute inset-0 ${spin ? 'animate-windmill motion-reduce:animate-none' : ''}`}
        style={{
          transformOrigin: '67.87% 44.32%',
          rotate: 'y -15deg',
          filter: 'drop-shadow(0 1.5px 2px rgba(0,0,0,0.5))',
          willChange: 'transform',
        }}
      >
        <span className={`absolute inset-0 ${FLOW}`} style={maskStyle(bladesSvg)} />
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
