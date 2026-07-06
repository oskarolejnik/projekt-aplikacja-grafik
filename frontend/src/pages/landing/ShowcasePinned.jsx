import { useRef } from 'react'
import { GrafikVignette, WyplataVignette, KasaVignette, RezerwacjaVignette, ImprezyVignette } from './Vignettes'
import { useGsapScene, canPin } from './motionPro'

// Sekcja-bohater „Zobacz system przy pracy" — pinned feature-scroll (Apple/Linear):
// scena stoi w miejscu, a scroll przełącza kolejne moduły produktu (scrub). Jedna wielka
// powierzchnia po prawej, korzyść jednym zdaniem po lewej, złoty pasek postępu z boku.
// Reduced-motion / brak JS → statyczna, pionowa lista modułów (pełna treść, zero pinów).

const MODULY = [
  { klucz: 'grafik', tytul: 'Grafik układa się sam', korzysc: 'Tydzień pracy w 10 minut zamiast w niedzielny wieczór.',
    detal: 'Kwalifikacje, dyspozycyjność i prawo pracy pilnowane automatycznie.', V: GrafikVignette },
  { klucz: 'wyplaty', tytul: 'Godziny z RCP → wypłaty', korzysc: 'Koniec miesiąca bez kalkulatora — co do minuty.',
    detal: 'Odbicia spinają się ze stawkami; księgowa dostaje gotowy eksport.', V: WyplataVignette },
  { klucz: 'kasa', tytul: 'Rozliczenie dnia się zgadza', korzysc: 'Różnica kasowa podświetla się, zanim urośnie.',
    detal: 'Utarg z POS kontra terminal i gotówka — anomalie łapane od razu.', V: KasaVignette },
  { klucz: 'rezerwacje', tytul: 'Rezerwacje wpadają same', korzysc: 'Stoliki online bez prowizji, plan sali pod ręką.',
    detal: 'Gość rezerwuje sam, Ty widzisz salę i scoring no-show.', V: RezerwacjaVignette },
  { klucz: 'imprezy', tytul: 'Wesela i imprezy pod kontrolą', korzysc: 'Zapytanie zamykasz w minuty, nie w dni.',
    detal: 'Szkic oferty AI, zadatki z kasy, portal Pary Młodej z listą gości.', V: ImprezyVignette },
]
const N = MODULY.length

export default function ShowcasePinned() {
  const sekcjaRef = useRef(null)
  const stageRef = useRef(null)
  const tekstRefs = useRef([])
  const ekranRefs = useRef([])
  const kropkaRefs = useRef([])
  const fillRef = useRef(null)
  const aktywny = useRef(0)

  useGsapScene(sekcjaRef, (g, ST) => {
    const teksty = tekstRefs.current
    const ekrany = ekranRefs.current
    const kropki = kropkaRefs.current

    // Stan początkowy: tylko moduł 0 widoczny.
    teksty.forEach((el, i) => g.set(el, { opacity: i === 0 ? 1 : 0, y: i === 0 ? 0 : 24 }))
    ekrany.forEach((el, i) => g.set(el, { opacity: i === 0 ? 1 : 0, y: i === 0 ? 0 : 40, scale: i === 0 ? 1 : 0.96 }))

    const pokaz = (idx) => {
      if (idx === aktywny.current) return
      const poprz = aktywny.current
      aktywny.current = idx
      g.to(teksty[poprz], { opacity: 0, y: -18, duration: 0.4, ease: 'power2.in' })
      g.to(ekrany[poprz], { opacity: 0, y: -30, scale: 0.97, duration: 0.45, ease: 'power2.in' })
      g.fromTo(teksty[idx], { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out', delay: 0.05 })
      g.fromTo(ekrany[idx], { opacity: 0, y: 40, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.6, ease: 'power3.out', delay: 0.05 })
      kropki.forEach((k, i) => k && k.classList.toggle('aktywna', i === idx))
    }

    ST.create({
      trigger: sekcjaRef.current,
      start: 'top top',
      end: () => `+=${window.innerHeight * (N - 0.35)}`,
      pin: stageRef.current,
      anticipatePin: 1,
      invalidateOnRefresh: true,
      onUpdate: (self) => {
        const seg = self.progress * N
        const idx = Math.max(0, Math.min(N - 1, Math.floor(seg)))
        pokaz(idx)
        if (fillRef.current) fillRef.current.style.transform = `scaleY(${self.progress})`
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
                <p className="mt-2 max-w-md text-sm text-muted/70">{m.detal}</p>
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
        .sc-dot { transition: background-color .3s, transform .3s; }
        .sc-dot.aktywna { background-color: #C9A96A; transform: scale(1.5); }
        .sc-dot.aktywna ~ .sc-label, .sc-dot.aktywna + .sc-label { color: #F4F4F5; }
      `}</style>
      <div ref={stageRef} className="relative flex h-dvh items-center overflow-hidden">
        <div className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 sm:px-6 lg:grid-cols-[0.9fr_1.1fr]">
          {/* Lewa kolumna: pasek postępu + zmieniający się tekst */}
          <div className="relative flex gap-6">
            {/* Pionowy pasek postępu ze złotym wypełnieniem */}
            <div className="relative hidden w-px shrink-0 bg-white/[0.10] sm:block" style={{ minHeight: '11rem' }}>
              <div ref={fillRef} className="absolute inset-x-0 top-0 h-full origin-top bg-zloto" style={{ transform: 'scaleY(0)' }} />
            </div>
            <div className="min-w-0">
              <p className="mb-6 font-brand text-sm font-semibold text-muted">Zobacz system <span className="text-zloto">przy pracy</span></p>
              <div className="relative min-h-[13rem]">
                {MODULY.map((m, i) => (
                  <div key={m.klucz} ref={(el) => (tekstRefs.current[i] = el)}
                       className="absolute inset-0 will-change-transform">
                    <h3 className="font-brand text-[clamp(1.6rem,3vw,2.4rem)] font-bold leading-tight text-ink">{m.tytul}</h3>
                    <p className="mt-4 max-w-md text-lg leading-relaxed text-muted">{m.korzysc}</p>
                    <p className="mt-2 max-w-md text-sm leading-relaxed text-muted/70">{m.detal}</p>
                  </div>
                ))}
              </div>
              {/* Kropki modułów */}
              <div className="mt-8 flex items-center gap-2.5">
                {MODULY.map((m, i) => (
                  <span key={m.klucz} ref={(el) => (kropkaRefs.current[i] = el)}
                        className={`sc-dot h-1.5 w-1.5 rounded-full bg-white/25 ${i === 0 ? 'aktywna' : ''}`} />
                ))}
              </div>
            </div>
          </div>

          {/* Prawa kolumna: duża powierzchnia produktu (moduły w stosie, crossfade) */}
          <div className="relative mx-auto h-[22rem] w-full max-w-lg sm:h-[26rem]">
            {MODULY.map((m, i) => (
              <div key={m.klucz} ref={(el) => (ekranRefs.current[i] = el)}
                   className="absolute inset-0 flex items-center will-change-transform">
                <div className="w-full"><m.V /></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
