import { useRef } from 'react'
import { GrafikVignette, WyplataVignette, KasaVignette, RezerwacjaVignette, ImprezyVignette } from './Vignettes'
import { useGsapScene, canPin } from './motionPro'

// TRASA 3D PRODUKTU — centerpiece „mockupy w 3D". Perspektywiczny korytarz: powierzchnie
// produktu wiszą w głębi jedna za drugą; scroll (pin) przelatuje przez nie „kamerą" (świat
// jedzie w Z). Każdy moduł wchodzi na focus (perspektywa sama go powiększa), pojawia się
// jedno zdanie korzyści, panele w głębi są ciemniejsze i rozmyte. Czysty CSS 3D + GSAP
// (research: najkrispowszy tekst + niezawodność). Mobile/reduced-motion → statyczna lista.

const MODULY = [
  { klucz: 'grafik',     tytul: 'Grafik układa się sam',        korzysc: 'Tydzień pracy w 10 minut, nie w niedzielny wieczór.', V: GrafikVignette },
  { klucz: 'wyplaty',    tytul: 'Godziny z RCP → wypłaty',      korzysc: 'Koniec miesiąca bez kalkulatora — co do minuty.',      V: WyplataVignette },
  { klucz: 'kasa',       tytul: 'Rozliczenie dnia się zgadza',  korzysc: 'Różnica kasowa świeci, zanim urośnie.',                V: KasaVignette },
  { klucz: 'rezerwacje', tytul: 'Rezerwacje wpadają same',      korzysc: 'Stoliki online bez prowizji, plan sali pod ręką.',     V: RezerwacjaVignette },
  { klucz: 'imprezy',    tytul: 'Wesela i imprezy pod kontrolą', korzysc: 'Zapytanie zamykasz w minuty, nie w dni.',             V: ImprezyVignette },
]
const N = MODULY.length

const PERSP = 1500     // głębia perspektywy (px)
const STEP = 640       // odstęp paneli w osi Z (mniejszy → więcej głębi widać naraz)
const YOFF = 46        // panele głębsze są wyżej → korytarz biegnie po skosie (widać głębię)
const clamp = (v, a, b) => Math.max(a, Math.min(b, v))

export default function ProductTour3D() {
  const sekcjaRef = useRef(null)
  const stageRef = useRef(null)
  const worldRef = useRef(null)
  const panelRefs = useRef([])
  const naglRefs = useRef([])
  const korRefs = useRef([])
  const kropkaRefs = useRef([])
  const fillRef = useRef(null)
  const aktywny = useRef(-1)

  useGsapScene(sekcjaRef, (g, ST) => {
    const world = worldRef.current
    const panele = panelRefs.current
    const nagl = naglRefs.current, kor = korRefs.current, kropki = kropkaRefs.current

    nagl.forEach((el, i) => g.set(el, { opacity: i === 0 ? 1 : 0, y: i === 0 ? 0 : 26 }))
    kor.forEach((el, i) => g.set(el, { opacity: i === 0 ? 1 : 0, y: i === 0 ? 0 : 22 }))

    const pokazTekst = (idx) => {
      if (idx === aktywny.current) return
      const p = aktywny.current
      aktywny.current = idx
      if (p >= 0) {
        g.to(nagl[p], { opacity: 0, y: -22, duration: 0.35, ease: 'power2.in' })
        g.to(kor[p], { opacity: 0, y: -18, duration: 0.35, ease: 'power2.in' })
      }
      g.fromTo(nagl[idx], { opacity: 0, y: 26 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out' })
      g.fromTo(kor[idx], { opacity: 0, y: 22 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out', delay: 0.05 })
      kropki.forEach((k, i) => k && k.classList.toggle('aktywna', i === idx))
    }

    const render = (progress) => {
      const worldZ = progress * (N - 1) * STEP
      const worldY = progress * (N - 1) * YOFF   // kontr-przesunięcie → focus zostaje wyśrodkowany
      world.style.transform = `translateZ(${worldZ.toFixed(1)}px) translateY(${worldY.toFixed(1)}px)`
      panele.forEach((el, i) => {
        if (!el) return
        const ze = worldZ - i * STEP            // Z panelu względem płaszczyzny kamery (0 = focus)
        let op, blur
        if (ze > 0) {                            // przeleciał przez focus → szybko gaśnie
          op = clamp(1 - ze / 340, 0, 1)
          blur = clamp(ze / 55, 0, 14)
        } else {                                 // w głębi → ciemniejszy i lekko rozmyty (widać korytarz)
          op = clamp(1 + ze / 2300, 0.12, 1)
          blur = clamp(-ze / 300, 0, 8)
        }
        // Kwantyzacja + cache: filter:blur() jest DROGI (re-rasteryzacja) — piszemy tylko przy
        // realnej zmianie. Blur skokowo co 0.5px, zIndex/opacity też bez zbędnych zapisów.
        const last = el._pt || (el._pt = {})
        const opR = Math.round(op * 100) / 100
        if (last.op !== opR) { el.style.opacity = String(opR); last.op = opR }
        const blurR = Math.round(blur * 2) / 2
        if (last.blur !== blurR) { el.style.filter = blurR > 0.2 ? `blur(${blurR}px)` : 'none'; last.blur = blurR }
        const zi = 1000 + Math.round(ze / 8)
        if (last.zi !== zi) { el.style.zIndex = String(zi); last.zi = zi }
      })
      if (fillRef.current) fillRef.current.style.transform = `scaleX(${progress.toFixed(3)})`
      pokazTekst(clamp(Math.round(progress * (N - 1)), 0, N - 1))
    }

    render(0)
    ST.create({
      trigger: sekcjaRef.current,
      start: 'top top',
      end: () => `+=${window.innerHeight * (N + 1.3)}`,
      pin: stageRef.current,
      anticipatePin: 1,
      invalidateOnRefresh: true,
      onUpdate: (self) => render(self.progress),
    })
  }, canPin())

  const anim = canPin()

  // ── Wariant mobile / reduced-motion: premium karty z reveal-on-scroll (apple mobile) ──
  if (!anim) {
    return (
      <section id="mozliwosci" className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
        <h2 data-head className="font-brand text-[clamp(2rem,7.5vw,3rem)] font-bold leading-[1.05] tracking-tight" style={{ textWrap: 'balance' }}>
          Zobacz system <span className="text-zloto-2">przy pracy</span>.
        </h2>
        <div className="mt-9 space-y-5 sm:mt-14 sm:space-y-10">
          {MODULY.map((m) => (
            <div
              key={m.klucz}
              data-animate="scale"
              className="rounded-[1.75rem] border border-white/[0.08] bg-white/[0.025] p-5 shadow-[0_20px_44px_-28px_rgba(0,0,0,0.6)] sm:grid sm:grid-cols-2 sm:items-center sm:gap-9 sm:p-8"
            >
              <div className="sm:order-1">
                <h3 className="font-brand text-[clamp(1.4rem,6vw,2rem)] font-semibold leading-tight tracking-tight text-ink">{m.tytul}</h3>
                <p className="mt-2.5 text-[15px] leading-relaxed text-muted sm:text-lg">{m.korzysc}</p>
              </div>
              <div className="mt-5 sm:order-2 sm:mt-0"><m.V /></div>
            </div>
          ))}
        </div>
      </section>
    )
  }

  return (
    <section ref={sekcjaRef} id="mozliwosci" className="relative">
      <h2 className="sr-only">Zobacz system przy pracy</h2>
      <style>{`
        .pt-dot { height:6px; width:6px; border-radius:999px; background:rgba(255,255,255,0.22); transition:background-color .35s, width .35s; }
        .pt-dot.aktywna { background-color:#E7CF9B; width:22px; }
        .pt-panel { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; transform-style:preserve-3d; will-change:opacity, filter; }
      `}</style>
      <div ref={stageRef} className="relative flex h-dvh flex-col items-center justify-center overflow-hidden">
        {/* Scena 3D — korytarz paneli produktu */}
        <div className="relative w-full max-w-xl px-6" style={{ perspective: `${PERSP}px`, perspectiveOrigin: '50% 42%' }}>
          <div ref={worldRef} className="relative mx-auto h-[19rem] w-full will-change-transform sm:h-[23rem]" style={{ transformStyle: 'preserve-3d' }}>
            {MODULY.map((m, i) => (
              <div key={m.klucz} ref={(el) => (panelRefs.current[i] = el)} className="pt-panel"
                   style={{ transform: `translateZ(${-i * STEP}px) translateY(${-i * YOFF}px)` }} aria-hidden={i !== 0}>
                <div className="w-full"><m.V /></div>
              </div>
            ))}
          </div>
        </div>

        {/* Tekst — nagłówek + korzyść (wymieniane) */}
        <div className="relative mt-10 h-[3.2rem] w-full max-w-3xl px-6 text-center sm:h-[3.8rem]">
          {MODULY.map((m, i) => (
            <h3 key={m.klucz} ref={(el) => (naglRefs.current[i] = el)}
                className="absolute inset-x-0 top-0 font-brand text-[clamp(1.6rem,3.6vw,2.7rem)] font-bold leading-tight tracking-tight text-ink will-change-transform">
              {m.tytul}
            </h3>
          ))}
        </div>
        <div className="relative mt-3 h-[3rem] w-full max-w-xl px-6 text-center">
          {MODULY.map((m, i) => (
            <p key={m.klucz} ref={(el) => (korRefs.current[i] = el)}
               className="absolute inset-x-0 top-0 font-switzer text-[clamp(1rem,1.5vw,1.2rem)] leading-relaxed text-muted will-change-transform">
              {m.korzysc}
            </p>
          ))}
        </div>

        {/* Kropki + pasek postępu */}
        <div className="mt-7 flex items-center gap-2.5">
          {MODULY.map((m, i) => (
            <span key={m.klucz} ref={(el) => (kropkaRefs.current[i] = el)} className={`pt-dot ${i === 0 ? 'aktywna' : ''}`} />
          ))}
        </div>
        <div className="absolute inset-x-0 bottom-0 h-[2px] bg-white/[0.06]">
          <div ref={fillRef} className="h-full origin-left bg-zloto" style={{ transform: 'scaleX(0)' }} />
        </div>
      </div>
    </section>
  )
}
