import { useRef } from 'react'
import { Logo } from '../../components/Logo'
import { useGsapScene, canPin } from './motionPro'

// Scena „chaos → porządek" (pinned, scrub): rozsypane narzędzia (Excel, kartki, kalkulator…)
// zbiegają się do środka i gasną, a nagłówek bólu przechodzi w ulgę — „Jeden system".
// Reduced-motion / brak JS → statyczny, spokojny wariant (bez pinu).

const CHAOS = [
  { t: 'Excel', x: -270, y: -66, r: -8 },
  { t: 'Papierowy grafik', x: 220, y: -96, r: 7 },
  { t: 'Kalkulator wypłat', x: -196, y: 74, r: 5 },
  { t: 'WhatsApp od zespołu', x: 250, y: 66, r: -6 },
  { t: 'Kartki za barem', x: -24, y: -134, r: -4 },
  { t: 'Trzy kartki rezerwacji', x: 44, y: 126, r: 9 },
]

export default function PainRelief() {
  const sekcjaRef = useRef(null)
  const stageRef = useRef(null)

  useGsapScene(sekcjaRef, (g) => {
    g.set('.pr-chip', { x: (i, el) => +el.dataset.x, y: (i, el) => +el.dataset.y, rotate: (i, el) => +el.dataset.r })
    g.set('.pr-relief', { opacity: 0, scale: 0.82 })
    g.set('.pr-relief-line', { opacity: 0, y: 22 })

    const tl = g.timeline({
      scrollTrigger: { trigger: sekcjaRef.current, start: 'top top', end: '+=140%', pin: stageRef.current, scrub: 0.6, anticipatePin: 1, invalidateOnRefresh: true },
    })
    tl.to('.pr-chip', { x: 0, y: 0, rotate: 0, scale: 0.35, opacity: 0, ease: 'power2.in', stagger: 0.04 }, 0)
      .to('.pr-pain-line', { opacity: 0, y: -24, ease: 'power2.in' }, 0.05)
      .to('.pr-relief', { opacity: 1, scale: 1, ease: 'power3.out' }, 0.35)
      .to('.pr-relief-line', { opacity: 1, y: 0, ease: 'power3.out' }, 0.45)
  }, canPin())

  // ── Wariant mobile / reduced-motion: chaos → ulga jako scroll-story (apple mobile) ──
  if (!canPin()) {
    return (
      <section className="mx-auto w-full max-w-2xl px-4 py-20 sm:px-6 sm:py-28">
        <p data-head className="font-brand text-[clamp(1.5rem,6.5vw,2.2rem)] font-medium leading-tight tracking-tight text-muted" style={{ textWrap: 'balance' }}>
          Dziś to <span className="text-ink">sześć</span> różnych miejsc.
        </p>
        <div className="mt-6 flex flex-wrap gap-2.5">
          {CHAOS.map((c) => (
            <span key={c.t} data-animate className="rounded-full border border-white/[0.10] bg-white/[0.04] px-4 py-2 text-[13px] font-medium text-muted backdrop-blur-sm sm:text-sm">
              {c.t}
            </span>
          ))}
        </div>
        <div data-animate="scale" className="mt-10 flex flex-col items-center gap-5 rounded-[2rem] border border-zloto/25 bg-wegiel px-6 py-11 text-center shadow-cta sm:mt-12 sm:py-14">
          <div className="inline-flex items-center gap-2.5 rounded-2xl border border-zloto/30 bg-noc/60 px-4 py-2.5">
            <Logo className="h-6" variant="gradient" />
            <span className="font-brand text-base font-bold text-ink">Jeden system</span>
          </div>
          <h2 className="font-brand text-[clamp(1.9rem,7.5vw,2.9rem)] font-bold leading-[1.05] tracking-tight" style={{ textWrap: 'balance' }}>
            To znika. <span className="text-zloto">Jeden</span> prowadzi cały lokal.
          </h2>
        </div>
      </section>
    )
  }

  return (
    <section ref={sekcjaRef} className="relative">
      <div ref={stageRef} className="relative flex h-dvh flex-col items-center justify-center overflow-hidden px-4">
        {/* Warstwa scalania: rozsypane narzędzia zbiegają w jeden rdzeń */}
        <div className="relative mb-10 grid h-[18rem] w-full max-w-3xl place-items-center">
          {CHAOS.map((c) => (
            <span key={c.t} data-x={c.x} data-y={c.y} data-r={c.r}
              className="pr-chip absolute whitespace-nowrap rounded-full border border-white/[0.10] bg-white/[0.04] px-4 py-2 text-sm font-medium text-muted backdrop-blur-sm will-change-transform">
              {c.t}
            </span>
          ))}
          <div className="pr-relief absolute inline-flex items-center gap-2.5 rounded-2xl border border-zloto/30 bg-wegiel px-5 py-3.5 shadow-cta will-change-transform">
            <Logo className="h-7" variant="gradient" />
            <span className="font-brand text-lg font-bold text-ink">Jeden system</span>
          </div>
        </div>

        {/* Nagłówek: ból → ulga (crossfade w miejscu) */}
        <div className="relative mx-auto max-w-3xl text-center">
          <p className="pr-pain-line font-brand text-xl font-medium text-muted sm:text-2xl" style={{ textWrap: 'balance' }}>
            Grafik w niedzielny wieczór. Wypłaty na kalkulatorze. Rezerwacje na trzech kartkach.
          </p>
          <h2 className="pr-relief-line absolute inset-x-0 top-0 font-brand text-3xl font-bold sm:text-4xl" style={{ textWrap: 'balance' }}>
            To znika. <span className="text-zloto">Jeden system</span> prowadzi cały lokal.
          </h2>
        </div>
      </div>
    </section>
  )
}
