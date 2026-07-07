import { useEffect, useRef } from 'react'
import { Icon } from '../../lib/icons'
import { useGsapScene, gsap, reducedMotion } from './motionPro'

// Sekcja „Cross-platform" — Lokalo Noir (DESIGN.md §8). Trzy urządzenia (tablet · laptop ·
// telefon) w PRZESTRZENI 3D (perspektywa): różne głębokości, cała scena przechyla się do
// kursora (parallax), a przy wejściu w kadr urządzenia SKŁADAJĄ SIĘ z głębi. Dekoracja: aria-hidden.

const Z_PLAT = { tablet: -140, laptop: 0, phone: 150 }

const PLATFORMY = ['iOS', 'Android', 'Windows', 'macOS', 'Web (PWA)', 'Tablet']

const CHECKI = [
  'Offline-friendly PWA',
  'Powiadomienia push',
  'Jeden system — zero ręcznych synchronizacji',
]

// Szkicowe „paski" i „kafle" wnętrza ekranów — bez tekstu, tylko rytm powierzchni.
function Pasek({ w = 'w-2/3' }) {
  return <div className={`h-1.5 rounded-full bg-white/[0.06] ${w}`} />
}

function Kafel({ h = 'h-8' }) {
  return <div className={`${h} rounded-md bg-white/[0.06]`} />
}

function ZlotaLinia({ w = 'w-12' }) {
  return <div className={`h-0.5 rounded-full bg-zloto/70 ${w}`} />
}

export default function SekcjaPlatformy() {
  const sekcjaRef = useRef(null)
  const sceneRef = useRef(null)
  const tiltRef = useRef(null)

  // Składanie urządzeń z głębi przy wejściu sekcji w kadr (scroll-triggered, raz).
  useGsapScene(sekcjaRef, (g) => {
    g.set('.plat-tablet', { opacity: 0, z: Z_PLAT.tablet - 300, rotateY: 14 })
    g.set('.plat-laptop', { opacity: 0, z: Z_PLAT.laptop - 300 })
    g.set('.plat-phone', { opacity: 0, z: Z_PLAT.phone - 300, rotateY: -12 })
    const tl = g.timeline({
      scrollTrigger: { trigger: sceneRef.current, start: 'top 78%', once: true },
      defaults: { ease: 'power3.out' },
    })
    tl.to('.plat-laptop', { opacity: 1, z: Z_PLAT.laptop, duration: 1.05 }, 0)
      .to('.plat-tablet', { opacity: 1, z: Z_PLAT.tablet, duration: 1.0 }, 0.12)
      .to('.plat-phone', { opacity: 1, z: Z_PLAT.phone, duration: 0.95 }, 0.22)
  })

  // Cała scena urządzeń przechyla się w 3D w stronę kursora (parallax głębi).
  useEffect(() => {
    if (reducedMotion() || typeof window === 'undefined') return
    const scene = sceneRef.current, tilt = tiltRef.current
    if (!scene || !tilt) return
    const rx = gsap.quickTo(tilt, 'rotationX', { duration: 0.8, ease: 'power3.out' })
    const ry = gsap.quickTo(tilt, 'rotationY', { duration: 0.8, ease: 'power3.out' })
    const onMove = (e) => {
      const r = scene.getBoundingClientRect()
      ry(((e.clientX - r.left - r.width / 2) / r.width) * 8)
      rx(-((e.clientY - r.top - r.height / 2) / r.height) * 6)
    }
    const onLeave = () => { rx(0); ry(0) }
    scene.addEventListener('pointermove', onMove)
    scene.addEventListener('pointerleave', onLeave)
    return () => { scene.removeEventListener('pointermove', onMove); scene.removeEventListener('pointerleave', onLeave) }
  }, [])

  return (
    <section ref={sekcjaRef} id="platformy" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2
          data-head=""
          className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl"
          style={{ textWrap: 'balance' }}
        >
          Działa <span className="whitespace-nowrap"><span className="text-zloto">wszędzie</span>,</span> gdzie Twój zespół.
        </h2>
        <p data-rv="" style={{ '--i': 1 }} className="mt-4 max-w-2xl text-muted">
          Personel ma aplikację zawsze pod ręką — instaluje się prosto z przeglądarki,{' '}
          <em className="font-editorial italic font-medium text-zloto-2">
            bez sklepów i bez działu IT
          </em>
          . Desktop dla biura, tablet na sali, telefon w kieszeni kelnera.
        </p>

        {/* Kompozycja urządzeń w 3D: tablet (głębia) · laptop (środek) · telefon (front) */}
        <div ref={sceneRef} aria-hidden className="relative mt-14" style={{ perspective: '1400px', perspectiveOrigin: '50% 58%' }}>
          <div ref={tiltRef} className="relative flex items-end justify-center will-change-transform" style={{ transformStyle: 'preserve-3d' }}>
          {/* Tablet ~4:3 */}
          <div className="plat-tablet relative z-0 -mr-8 mb-3 w-32 shrink-0 sm:-mr-10 sm:w-56">
            <div className="glass aspect-[4/3] rounded-2xl p-2 sm:p-3">
              <div className="flex h-full flex-col gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
                <div className="flex items-center justify-between">
                  <Pasek w="w-1/3" />
                  <ZlotaLinia w="w-8" />
                </div>
                <div className="grid flex-1 grid-cols-2 gap-1.5">
                  <Kafel h="h-auto" />
                  <Kafel h="h-auto" />
                  <Kafel h="h-auto" />
                  <Kafel h="h-auto" />
                </div>
              </div>
            </div>
          </div>

          {/* Laptop / desktop: ekran z belką i 3 kropkami + podstawa */}
          <div className="plat-laptop relative z-10 w-52 shrink-0 sm:w-[400px]">
            <div className="glass overflow-hidden rounded-2xl">
              <div className="flex items-center gap-1.5 border-b border-white/[0.08] px-3 py-2.5">
                <span className="h-2 w-2 rounded-full bg-white/[0.09]" />
                <span className="h-2 w-2 rounded-full bg-white/[0.09]" />
                <span className="h-2 w-2 rounded-full bg-white/[0.09]" />
              </div>
              <div className="grid grid-cols-[auto_1fr] gap-3 p-3 sm:p-4">
                <div className="w-8 space-y-1.5 sm:w-12">
                  <Pasek w="w-full" />
                  <Pasek w="w-full" />
                  <Pasek w="w-2/3" />
                  <Pasek w="w-full" />
                </div>
                <div className="space-y-2">
                  <div className="grid grid-cols-3 gap-1.5">
                    <Kafel h="h-9 sm:h-12" />
                    <Kafel h="h-9 sm:h-12" />
                    <Kafel h="h-9 sm:h-12" />
                  </div>
                  <div className="flex items-end gap-1 pt-1">
                    {[5, 8, 6, 10, 12, 9, 7].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-t bg-white/[0.06]"
                        style={{ height: `${h * 3}px` }}
                      />
                    ))}
                  </div>
                  <ZlotaLinia w="w-full" />
                  <Pasek w="w-1/2" />
                </div>
              </div>
            </div>
            <div className="relative left-1/2 h-2 w-[112%] -translate-x-1/2 rounded-b-xl border border-white/[0.10] bg-white/[0.04]" />
          </div>

          {/* Telefon pion ~9:19 z paskiem-notchem */}
          <div className="plat-phone relative z-20 -ml-7 w-16 shrink-0 sm:-ml-9 sm:w-24">
            <div className="glass flex aspect-[9/19] flex-col rounded-[1.5rem] p-1.5 sm:p-2">
              <div className="mx-auto mt-1 h-1 w-8 rounded-full bg-white/[0.09]" />
              <div className="mt-2 flex flex-1 flex-col gap-1.5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-2">
                <Pasek w="w-2/3" />
                <Kafel h="h-7" />
                <Kafel h="h-7" />
                <ZlotaLinia w="w-8" />
                <Pasek w="w-full" />
                <Pasek w="w-3/4" />
                <div className="mt-auto h-5 rounded-md bg-zloto/10" />
              </div>
            </div>
          </div>
          </div>
        </div>

        {/* Ciche chipy platform */}
        <ul data-rv="" style={{ '--i': 3 }} className="mt-12 flex flex-wrap justify-center gap-2">
          {PLATFORMY.map((p) => (
            <li
              key={p}
              className="rounded-full border border-white/[0.10] bg-white/[0.02] px-3.5 py-1.5 text-xs font-medium text-muted"
            >
              {p}
            </li>
          ))}
        </ul>

        {/* Trzy konkrety */}
        <div className="mt-8 flex flex-col items-center justify-center gap-3 border-t border-white/[0.08] pt-8 sm:flex-row sm:gap-10">
          {CHECKI.map((c, i) => (
            <div
              key={c}
              data-rv=""
              style={{ '--i': 4 + i }}
              className="flex items-center gap-2.5 text-sm text-muted"
            >
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-mint/15">
                <Icon name="check" className="h-3.5 w-3.5 text-mint" />
              </span>
              {c}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
