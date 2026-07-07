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

// Głębia paneli produktu (translateZ). Panel rez z tyłu, grafik na wprost, telefon z przodu.
const Z_REST = { rez: -90, grafik: 0, tel: 110 }

export default function HeroPro() {
  const scopeRef = useRef(null)
  const stackRef = useRef(null)
  const tiltRef = useRef(null)

  // Choreografia wejścia (pierwsze ładowanie). Panele produktu SKŁADAJĄ SIĘ z głębi 3D.
  useGsapScene(scopeRef, (g) => {
    g.set('.hero-line', { yPercent: 115 })
    g.set(['.hero-sub', '.hero-cta', '.hero-cue'], { opacity: 0, y: 22 })
    g.set('.hero-gold', { opacity: 0 })
    g.set('.hero-rez', { opacity: 0, z: Z_REST.rez, rotateY: 12, rotateZ: -3 })
    g.set('.hero-grafik', { opacity: 0, z: Z_REST.grafik })
    g.set('.hero-tel', { opacity: 0, z: Z_REST.tel, rotateY: -8, rotateZ: 1 })

    const tl = g.timeline({ defaults: { ease: 'power4.out' } })
    tl.to('.hero-line', { yPercent: 0, duration: 0.95, stagger: 0.12 }, 0.1)
      .to('.hero-gold', { opacity: 1, duration: 0.9, ease: 'power2.out' }, 0.7)
      .to('.hero-sub', { opacity: 1, y: 0, duration: 0.7 }, 0.55)
      .to('.hero-cta', { opacity: 1, y: 0, duration: 0.6 }, 0.7)
      .to('.hero-cue', { opacity: 1, y: 0, duration: 0.6 }, 1.0)
      // panele wlatują z głębi (z −360 do rest), gasnąc-rozjaśniając, ze staggerem
      .fromTo('.hero-grafik', { opacity: 0, z: Z_REST.grafik - 360 }, { opacity: 1, z: Z_REST.grafik, duration: 1.15, ease: 'power3.out' }, 0.4)
      .fromTo('.hero-rez', { opacity: 0, z: Z_REST.rez - 360 }, { opacity: 0.92, z: Z_REST.rez, duration: 1.05, ease: 'power3.out' }, 0.62)
      .fromTo('.hero-tel', { opacity: 0, z: Z_REST.tel - 360 }, { opacity: 1, z: Z_REST.tel, duration: 1.0, ease: 'power3.out' }, 0.8)
  })

  // Pointer: cała scena produktu przechyla się w 3D w stronę kursora (płynnie, quickTo) —
  // głębia paneli (translateZ) ujawnia się jako realny parallax. Reduced-motion → brak.
  useEffect(() => {
    if (reducedMotion() || typeof window === 'undefined') return
    const stack = stackRef.current, tilt = tiltRef.current
    if (!stack || !tilt) return
    const rx = gsap.quickTo(tilt, 'rotationX', { duration: 0.8, ease: 'power3.out' })
    const ry = gsap.quickTo(tilt, 'rotationY', { duration: 0.8, ease: 'power3.out' })
    const onMove = (e) => {
      const r = stack.getBoundingClientRect()
      const dx = (e.clientX - r.left - r.width / 2) / r.width
      const dy = (e.clientY - r.top - r.height / 2) / r.height
      ry(dx * 9); rx(-dy * 7)
    }
    const onLeave = () => { rx(0); ry(0) }
    stack.addEventListener('pointermove', onMove)
    stack.addEventListener('pointerleave', onLeave)
    return () => { stack.removeEventListener('pointermove', onMove); stack.removeEventListener('pointerleave', onLeave) }
  }, [])

  return (
    <section ref={scopeRef} className="relative overflow-hidden">
      <style>{`
        .hero-magnes { transform: translate(var(--tx,0), var(--ty,0)); transition: transform .35s cubic-bezier(.22,1,.36,1); will-change: transform; }
        .hero-cue-dot { animation: heroCue 1.9s cubic-bezier(.22,1,.36,1) infinite; }
        @keyframes heroCue { 0% { transform: translateY(-12px); opacity: 0 } 28% { opacity: 1 } 100% { transform: translateY(40px); opacity: 0 } }
        @media (prefers-reduced-motion: reduce) {
          .hero-magnes { transform: none !important; transition: none !important; }
          .hero-cue-dot { animation: none; }
        }
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
          <p className="hero-cta mt-3 flex items-center gap-2 text-xs text-muted">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-zloto" />
            Pierwsze 14 dni za darmo — obciążamy dopiero po 14 dniach.
          </p>
        </div>

        {/* Scena produktu w 3D — panele na różnych głębokościach, cała scena przechyla się
            w perspektywie w stronę kursora (realny parallax). Składa się z głębi na wejściu. */}
        {/* max-sm: kotwiczymy perspective-origin do PRAWEJ krawędzi kontenera — panel telefonu
            (translateZ 110) skaluje się wtedy DO WEWNĄTRZ, nie poza brzeg → koniec ucięcia na
            telefonie (zmierzony zapas ~10px, niezależny od szerokości 320–430px). Desktop (≥sm)
            bez zmian: domyślne perspective-origin 50% 50%, perspektywa 1300px. */}
        <div ref={stackRef} className="relative mx-auto w-full max-w-md max-sm:max-w-[20rem] max-sm:[perspective-origin:100%_50%] lg:max-w-none" style={{ perspective: '1300px' }}>
          <div ref={tiltRef} className="relative will-change-transform" style={{ transformStyle: 'preserve-3d' }}>
            <div className="hero-rez absolute -left-14 -top-24 z-0 hidden w-60 xl:block">
              <div className="max-h-60 overflow-hidden" style={{ maskImage: 'linear-gradient(180deg,#000 62%,transparent 96%)', WebkitMaskImage: 'linear-gradient(180deg,#000 62%,transparent 96%)' }}>
                <RezerwacjaVignette />
              </div>
            </div>
            <div className="hero-grafik relative z-10">
              <GrafikVignette />
            </div>
            {/* max-sm: na telefonie panel mniejszy (w-32) i wsunięty do wnętrza (right-[10px], apple
                inset nachodzący na dolny-prawy róg grafiku); ≥sm wraca 1:1 do obecnego wyglądu w rogu. */}
            {/* Na telefonie chowamy nakładający się panel-telefon (nachodził na ~40% grafiku =
                „rozjechane"); mobile pokazuje czysty, pojedynczy kadr grafiku. ≥sm wraca panel w rogu. */}
            <div className="hero-tel absolute -bottom-10 -right-3 z-20 hidden w-36 sm:block sm:-right-6 sm:w-40">
              <TelefonPortfel />
            </div>
          </div>
        </div>
      </div>

      {/* Subtelny cue scrolla — złota kropka schodzi po włoskowatej linii. */}
      <div aria-hidden className="hero-cue pointer-events-none absolute bottom-6 left-1/2 z-10 hidden h-10 w-px -translate-x-1/2 overflow-hidden bg-white/10 lg:block">
        <span className="hero-cue-dot absolute inset-x-0 top-0 h-3 bg-zloto" />
      </div>
    </section>
  )
}
