import { useRef } from 'react'
import { GrafikVignette, WyplataVignette, KasaVignette, RezerwacjaVignette, ImprezyVignette } from './Vignettes'
import { useGsapScene, canPin } from './motionPro'

// Sekcja-bohater „Zobacz system przy pracy" — pinned, kinowa (Apple-like): scena stoi,
// a scroll przełącza moduły produktu. Kompozycja WYŚRODKOWANA: wielki nagłówek + jedno
// zdanie korzyści + duże okno produktu (bohater), które WJEŻDŻA z dołu (slide+scale+blur).
// Reduced-motion / mobile / brak JS → statyczna, pionowa lista modułów.

const MODULY = [
  { klucz: 'grafik',     tytul: 'Grafik układa się sam',        korzysc: 'Tydzień pracy w 10 minut, nie w niedzielny wieczór.', V: GrafikVignette },
  { klucz: 'wyplaty',    tytul: 'Godziny z RCP → wypłaty',      korzysc: 'Koniec miesiąca bez kalkulatora — co do minuty.',      V: WyplataVignette },
  { klucz: 'kasa',       tytul: 'Rozliczenie dnia się zgadza',  korzysc: 'Różnica kasowa świeci, zanim urośnie.',                V: KasaVignette },
  { klucz: 'rezerwacje', tytul: 'Rezerwacje wpadają same',      korzysc: 'Stoliki online bez prowizji, plan sali pod ręką.',     V: RezerwacjaVignette },
  { klucz: 'imprezy',    tytul: 'Wesela i imprezy pod kontrolą', korzysc: 'Zapytanie zamykasz w minuty, nie w dni.',             V: ImprezyVignette },
]
const N = MODULY.length

export default function ShowcasePinned() {
  const sekcjaRef = useRef(null)
  const stageRef = useRef(null)
  const naglRefs = useRef([])
  const korRefs = useRef([])
  const oknoRefs = useRef([])
  const kropkaRefs = useRef([])
  const fillRef = useRef(null)
  const aktywny = useRef(0)

  useGsapScene(sekcjaRef, (g, ST) => {
    const nagl = naglRefs.current, kor = korRefs.current, okna = oknoRefs.current, kropki = kropkaRefs.current

    // Stan początkowy: moduł 0 widoczny, reszta poniżej i rozmyta.
    nagl.forEach((el, i) => g.set(el, { opacity: i === 0 ? 1 : 0, y: i === 0 ? 0 : 40 }))
    kor.forEach((el, i) => g.set(el, { opacity: i === 0 ? 1 : 0, y: i === 0 ? 0 : 30 }))
    okna.forEach((el, i) => g.set(el, { opacity: i === 0 ? 1 : 0, y: i === 0 ? 0 : 70, scale: i === 0 ? 1 : 0.9, filter: i === 0 ? 'blur(0px)' : 'blur(12px)' }))

    const pokaz = (idx) => {
      if (idx === aktywny.current) return
      const p = aktywny.current
      aktywny.current = idx
      // Wyjście poprzedniego — do góry, gaśnie, lekko w tył.
      g.to(nagl[p], { opacity: 0, y: -34, duration: 0.4, ease: 'power2.in' })
      g.to(kor[p], { opacity: 0, y: -24, duration: 0.4, ease: 'power2.in' })
      g.to(okna[p], { opacity: 0, y: -50, scale: 0.97, filter: 'blur(8px)', duration: 0.45, ease: 'power2.in' })
      // Wejście nowego — z dołu, wyostrza się (blur→0), skala rośnie. „Apple arrival".
      g.fromTo(nagl[idx], { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.6, ease: 'power3.out', delay: 0.08 })
      g.fromTo(kor[idx], { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.6, ease: 'power3.out', delay: 0.14 })
      g.fromTo(okna[idx], { opacity: 0, y: 70, scale: 0.9, filter: 'blur(12px)' }, { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)', duration: 0.75, ease: 'power3.out', delay: 0.06 })
      kropki.forEach((k, i) => k && k.classList.toggle('aktywna', i === idx))
    }

    ST.create({
      trigger: sekcjaRef.current,
      start: 'top top',
      end: () => `+=${window.innerHeight * N}`,
      pin: stageRef.current,
      anticipatePin: 1,
      invalidateOnRefresh: true,
      onUpdate: (self) => {
        const idx = Math.max(0, Math.min(N - 1, Math.floor(self.progress * N * 0.999)))
        pokaz(idx)
        if (fillRef.current) fillRef.current.style.transform = `scaleX(${self.progress})`
      },
    })
  }, canPin())

  const anim = canPin()

  // ── Wariant statyczny (reduced-motion / mobile / brak JS): pionowa lista ──
  if (!anim) {
    return (
      <section id="mozliwosci" className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="max-w-2xl font-brand text-3xl font-bold sm:text-4xl" style={{ textWrap: 'balance' }}>
          Zobacz system <span className="text-zloto">przy pracy</span>.
        </h2>
        <div className="mt-12 space-y-16">
          {MODULY.map((m) => (
            <div key={m.klucz} className="grid items-center gap-8 lg:grid-cols-2">
              <div>
                <h3 className="font-brand text-2xl font-semibold text-ink">{m.tytul}</h3>
                <p className="mt-3 max-w-md text-lg text-muted">{m.korzysc}</p>
              </div>
              <div className="mx-auto w-full max-w-md"><m.V /></div>
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
        .sc-dot { height: 6px; width: 6px; border-radius: 999px; background: rgba(255,255,255,0.22); transition: background-color .35s, width .35s; }
        .sc-dot.aktywna { background-color: #C9A96A; width: 22px; }
      `}</style>
      <div ref={stageRef} className="relative flex h-dvh flex-col items-center justify-center overflow-hidden px-6">
        {/* Nagłówki (stos, wymieniane) */}
        <div className="relative h-[3.4rem] w-full max-w-3xl text-center sm:h-[4rem]">
          {MODULY.map((m, i) => (
            <h3 key={m.klucz} ref={(el) => (naglRefs.current[i] = el)}
                className="absolute inset-x-0 top-0 font-brand text-[clamp(1.7rem,4vw,3rem)] font-bold leading-tight tracking-tight text-ink will-change-transform">
              {m.tytul}
            </h3>
          ))}
        </div>
        {/* Korzyść (stos, wymieniane) */}
        <div className="relative mt-3 h-[3.5rem] w-full max-w-xl text-center sm:mt-4">
          {MODULY.map((m, i) => (
            <p key={m.klucz} ref={(el) => (korRefs.current[i] = el)}
               className="absolute inset-x-0 top-0 font-switzer text-[clamp(1rem,1.6vw,1.25rem)] leading-relaxed text-muted will-change-transform">
              {m.korzysc}
            </p>
          ))}
        </div>
        {/* Wielkie okno produktu — bohater sekcji (stos, wjeżdża z dołu) */}
        <div className="relative mt-8 h-[19rem] w-full max-w-xl sm:mt-10 sm:h-[23rem]">
          {MODULY.map((m, i) => (
            <div key={m.klucz} ref={(el) => (oknoRefs.current[i] = el)}
                 className="absolute inset-0 flex items-center justify-center will-change-transform">
              <div className="w-full"><m.V /></div>
            </div>
          ))}
        </div>
        {/* Kropki postępu */}
        <div className="mt-9 flex items-center gap-2.5">
          {MODULY.map((m, i) => (
            <span key={m.klucz} ref={(el) => (kropkaRefs.current[i] = el)} className={`sc-dot ${i === 0 ? 'aktywna' : ''}`} />
          ))}
        </div>
        {/* Cienki złoty pasek postępu na dole sceny */}
        <div className="absolute inset-x-0 bottom-0 h-[2px] bg-white/[0.06]">
          <div ref={fillRef} className="h-full origin-left bg-zloto" style={{ transform: 'scaleX(0)' }} />
        </div>
      </div>
    </section>
  )
}
