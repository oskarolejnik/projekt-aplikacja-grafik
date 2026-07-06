import { useEffect, useRef } from 'react'
import { GrafikVignette, RezerwacjaVignette } from './Vignettes'
import Ambient3D from './three/Ambient3D'
import { useGsapScene, gsap, reducedMotion } from './motionPro'

// Hero premium „Lokalo Noir" — warstwowa scena produktu z głębią (pointer-parallax),
// ambientowe złote bryły 3D w tle (leniwe, desktop-only) i choreografia wejścia GSAP:
// nagłówek wjeżdża liniami (clip-reveal), złoty akcent domyka scenę na końcu.

const MAIL = 'mailto:kontakt@grafikpracy.pl'

// Telefon pracownika — mały ekran „Twoje godziny" (najczęściej otwierany widok).
function TelefonPortfel() {
  return (
    <div aria-hidden className="overflow-hidden rounded-[1.9rem] border border-white/[0.14] bg-bg shadow-soft">
      <div className="flex justify-center pt-2.5"><span className="h-1.5 w-14 rounded-full bg-white/[0.10]" /></div>
      <div className="px-4 pb-4 pt-3">
        <div className="text-[10px] font-semibold text-muted">Twoje godziny · lipiec</div>
        <div className="mt-1 flex items-baseline gap-1">
          <span className="font-display text-2xl font-bold tabular-nums text-ink">168:30</span>
          <span className="text-[10px] text-muted">h</span>
        </div>
        <div className="mt-2.5 space-y-1">
          {[['Sala', '96:00'], ['Bar', '48:30'], ['Impreza', '24:00']].map(([l, h]) => (
            <div key={l} className="flex items-center justify-between text-[10px]">
              <span className="text-muted">{l}</span>
              <span className="font-mono font-bold tabular-nums text-ink">{h}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between gap-2 rounded-lg bg-mint/[0.10] px-2.5 py-1.5">
          <span className="whitespace-nowrap text-[10px] font-semibold text-muted">Wypłata</span>
          <span className="whitespace-nowrap font-display text-xs font-bold text-mint">4 380 zł</span>
        </div>
      </div>
    </div>
  )
}

// Magnetyczne CTA: przycisk lekko podąża za kursorem, wraca po zejściu.
function Magnes({ href, className = '', children }) {
  const move = (e) => {
    if (reducedMotion()) return
    const el = e.currentTarget
    const r = el.getBoundingClientRect()
    el.style.setProperty('--tx', `${((e.clientX - r.left - r.width / 2) * 0.16).toFixed(1)}px`)
    el.style.setProperty('--ty', `${((e.clientY - r.top - r.height / 2) * 0.28).toFixed(1)}px`)
  }
  const leave = (e) => {
    e.currentTarget.style.setProperty('--tx', '0px')
    e.currentTarget.style.setProperty('--ty', '0px')
  }
  return (
    <a href={href} onPointerMove={move} onPointerLeave={leave}
       className={`hero-magnes ${className}`}>{children}</a>
  )
}

export default function HeroPro() {
  const scopeRef = useRef(null)
  const stackRef = useRef(null)

  // Choreografia wejścia (pierwsze ładowanie, nie scroll). gsap.context sprząta sam.
  useGsapScene(scopeRef, (g) => {
    g.set('.hero-line', { yPercent: 115 })
    g.set(['.hero-sub', '.hero-cta'], { opacity: 0, y: 22 })
    g.set('.hero-gold', { opacity: 0 })
    g.set('.hero-stack', { opacity: 0, y: 48, scale: 0.955 })
    g.set('.hero-float', { opacity: 0, y: 30 })

    const tl = g.timeline({ defaults: { ease: 'power4.out' } })
    tl.to('.hero-line', { yPercent: 0, duration: 0.95, stagger: 0.12 }, 0.1)
      .to('.hero-gold', { opacity: 1, duration: 0.9, ease: 'power2.out' }, 0.7)
      .to('.hero-sub', { opacity: 1, y: 0, duration: 0.7 }, 0.55)
      .to('.hero-cta', { opacity: 1, y: 0, duration: 0.6 }, 0.7)
      .to('.hero-stack', { opacity: 1, y: 0, scale: 1, duration: 1.1, ease: 'power3.out' }, 0.45)
      .to('.hero-float', { opacity: 1, y: 0, duration: 0.8, stagger: 0.12, ease: 'power3.out' }, 0.85)
  })

  // Pointer-parallax warstw produktu: głębia sterowana kursorem (płynnie, quickTo).
  useEffect(() => {
    if (reducedMotion() || typeof window === 'undefined') return
    const stack = stackRef.current
    if (!stack) return
    const warstwy = stack.querySelectorAll('[data-depth]')
    const setters = Array.from(warstwy).map((el) => ({
      el,
      d: parseFloat(el.dataset.depth) || 0,
      x: gsap.quickTo(el, 'xPercent', { duration: 0.7, ease: 'power3.out' }),
      y: gsap.quickTo(el, 'yPercent', { duration: 0.7, ease: 'power3.out' }),
    }))
    const onMove = (e) => {
      const r = stack.getBoundingClientRect()
      const dx = (e.clientX - r.left - r.width / 2) / r.width
      const dy = (e.clientY - r.top - r.height / 2) / r.height
      setters.forEach((s) => { s.x(dx * s.d * 10); s.y(dy * s.d * 10) })
    }
    const onLeave = () => setters.forEach((s) => { s.x(0); s.y(0) })
    stack.addEventListener('pointermove', onMove)
    stack.addEventListener('pointerleave', onLeave)
    return () => { stack.removeEventListener('pointermove', onMove); stack.removeEventListener('pointerleave', onLeave) }
  }, [])

  return (
    <section ref={scopeRef} className="relative overflow-hidden">
      <style>{`
        .hero-magnes { transform: translate(var(--tx,0), var(--ty,0)); transition: transform .35s cubic-bezier(.22,1,.36,1); will-change: transform; }
        @media (prefers-reduced-motion: reduce) { .hero-magnes { transform: none !important; transition: none !important; } }
      `}</style>

      {/* Ambientowa, dyskretna poświata 3D — desktop-only, leniwe; na mobile zostaje złote światło CSS.
          Celowo bardzo stonowana (niska nieprzezroczystość, zmiękczona maska) — ma szeptać, nie krzyczeć. */}
      <Ambient3D className="pointer-events-none absolute inset-0 z-0 opacity-[0.35] [mask-image:radial-gradient(55%_55%_at_72%_38%,#000_18%,transparent_72%)]" />

      <div className="relative z-10 mx-auto grid w-full max-w-6xl items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:gap-10 lg:py-28">
        <div>
          <h1 className="font-brand text-[clamp(2.9rem,6.4vw,4.8rem)] font-bold leading-[1.0] tracking-tight">
            <span className="block overflow-hidden pb-[0.06em]"><span className="hero-line block">Cały lokal w</span></span>
            <span className="block overflow-hidden pb-[0.06em]"><span className="hero-line block">
              <span className="hero-gold text-zloto">jednym</span> systemie.
            </span></span>
          </h1>
          <p className="hero-sub mt-6 font-brand text-[clamp(1.15rem,2vw,1.6rem)] font-medium leading-tight text-muted">
            Zamiast Excela i pięciu apek.
          </p>

          <div className="hero-cta mt-9 flex flex-wrap gap-3">
            <Magnes href="?start" className="rounded-xl bg-zloto px-6 py-3.5 text-sm font-semibold text-noc transition-colors hover:bg-zloto-2">Zacznij za darmo</Magnes>
            <a href={`${MAIL}?subject=Demo%20Lokalo`} className="rounded-xl border border-white/[0.12] px-6 py-3.5 text-sm font-semibold text-ink transition hover:bg-white/[0.06] active:scale-[0.98]">Umów demo</a>
          </div>
        </div>

        {/* Warstwowa scena produktu — głębia + pointer-parallax */}
        <div ref={stackRef} className="relative mx-auto w-full max-w-md lg:max-w-none">
          <div className="hero-float absolute -left-14 -top-24 z-0 hidden w-60 -rotate-3 opacity-90 will-change-transform xl:block" data-depth="1.8">
            <div className="max-h-60 overflow-hidden" style={{ maskImage: 'linear-gradient(180deg,#000 62%,transparent 96%)', WebkitMaskImage: 'linear-gradient(180deg,#000 62%,transparent 96%)' }}>
              <RezerwacjaVignette />
            </div>
          </div>
          <div className="hero-stack relative z-10 will-change-transform" data-depth="0.5">
            <GrafikVignette />
          </div>
          <div className="hero-float absolute -bottom-10 -right-3 z-20 w-36 rotate-1 will-change-transform sm:-right-6 sm:w-40" data-depth="2.6">
            <TelefonPortfel />
          </div>
        </div>
      </div>
    </section>
  )
}
