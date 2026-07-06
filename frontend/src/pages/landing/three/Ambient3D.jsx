import { Suspense, lazy, useEffect, useRef, useState, Component } from 'react'
import { motionOn } from '../motionPro'

// Bramka + leniwe ładowanie ambientowej sceny 3D. three.js ładuje się DOPIERO gdy
// urządzenie się kwalifikuje (desktop z WebGL, bez reduced-motion) — na mobile/tablecie
// i przy oszczędzaniu ruchu nie ma go w ogóle (statyczne złote światło CSS pod spodem).
const Scene = lazy(() => import('./scene'))

function webglOK() {
  try {
    const c = document.createElement('canvas')
    return !!(window.WebGLRenderingContext && (c.getContext('webgl') || c.getContext('experimental-webgl')))
  } catch (_) {
    return false
  }
}

// Tylko desktop (pointer: fine), z WebGL, bez reduced-motion.
export function can3D() {
  if (typeof window === 'undefined' || !motionOn()) return false
  const fine = window.matchMedia && window.matchMedia('(pointer: fine)').matches
  return !!fine && webglOK()
}

// Utrata kontekstu WebGL / błąd sceny → cicho znika (zostaje statyczne tło CSS).
class Boundary extends Component {
  constructor(p) { super(p); this.state = { err: false } }
  static getDerivedStateFromError() { return { err: true } }
  render() { return this.state.err ? null : this.props.children }
}

export default function Ambient3D({ className = '' }) {
  const [ok] = useState(() => can3D())
  const wrapRef = useRef(null)
  // Płótno MONTUJEMY/odmontowujemy wg widoczności — dynamiczny frameloop 'always'→'never'
  // NIE działa (Canvas cache'uje wartość początkową), więc pauza = odmontowanie (zwalnia GPU).
  // Start: NIEzamontowane (montujemy dopiero po potwierdzeniu widoczności — brak eager-mountu
  // przy wejściu z kotwicą pod hero). Odmontowanie ZWLEKANE (~600 ms) → drobny jitter scrolla
  // na granicy nie thrashuje kontekstów WebGL (R3F v8 niszczy kontekst z 500 ms opóźnieniem).
  const [inView, setInView] = useState(false)

  useEffect(() => {
    if (!ok) return
    const el = wrapRef.current
    if (!el || !('IntersectionObserver' in window)) { setInView(true); return }
    let timer = 0
    const io = new IntersectionObserver(
      ([e]) => {
        clearTimeout(timer)
        if (e.isIntersecting) setInView(true)
        else timer = window.setTimeout(() => setInView(false), 600)
      },
      { rootMargin: '200px' },
    )
    io.observe(el)
    return () => { clearTimeout(timer); io.disconnect() }
  }, [ok])

  if (!ok) return null
  return (
    <div ref={wrapRef} aria-hidden className={className}>
      {inView && (
        <Boundary>
          <Suspense fallback={null}>
            <Scene />
          </Suspense>
        </Boundary>
      )}
    </div>
  )
}
