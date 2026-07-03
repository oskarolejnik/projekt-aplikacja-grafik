import { useEffect, useRef } from 'react'
import { GrafikVignette, RezerwacjaVignette } from './Vignettes'
import { animacjeWlaczone } from './motion'

// Kompozycja „ekosystemu" w hero: desktop (grafik) + telefon (portfel pracownika)
// + tablet (widget rezerwacji dla gościa). Ekrany celowo mówią językiem PRODUKTU
// (Cicha scena, mięta) — noir to rama sceny, nie treść ekranu.

// Telefon budowany w kodzie: własna rama (bez paska okna — to mobile), w środku
// skrót „Twoje godziny" — najczęściej otwierany ekran pracownika.
function TelefonPortfel({ className = '' }) {
  return (
    <div aria-hidden className={`overflow-hidden rounded-[1.9rem] border border-white/[0.14] bg-bg shadow-soft ${className}`}>
      <div className="flex justify-center pt-2.5">
        <span className="h-1.5 w-14 rounded-full bg-white/[0.10]" />
      </div>
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

export default function HeroEkosystem() {
  const scenaRef = useRef(null)
  const telefonRef = useRef(null)
  const tabletRef = useRef(null)

  // Miękka paralaksa warstw przy scrollu: telefon płynie szybciej, tablet wolniej —
  // głębia bez teatru. Pomiar na nieruchomej scenie, transform na warstwach
  // (ta sama zasada co słowo-tło cennika: inaczej offset narasta w pętli).
  useEffect(() => {
    if (!animacjeWlaczone()) return
    let raf = 0
    const tick = () => {
      raf = 0
      const scena = scenaRef.current
      if (!scena) return
      const r = scena.getBoundingClientRect()
      const od = r.top + r.height / 2 - window.innerHeight / 2
      if (telefonRef.current) telefonRef.current.style.transform = `translateY(${(-od * 0.07).toFixed(1)}px)`
      if (tabletRef.current) tabletRef.current.style.transform = `translateY(${(od * 0.05).toFixed(1)}px)`
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(tick) }
    // capture — na landingu scrolluje się BODY, zdarzenie nie bąbelkuje do window.
    window.addEventListener('scroll', onScroll, { passive: true, capture: true })
    tick()
    return () => { window.removeEventListener('scroll', onScroll, { capture: true }); if (raf) cancelAnimationFrame(raf) }
  }, [])

  return (
    <div ref={scenaRef} className="relative mx-auto w-full max-w-md lg:max-w-none">
      {/* Tablet z widgetem gościa — warstwa tylna; wystaje z lewej-góry na tyle,
          żeby było widać nagłówek „Zarezerwuj stolik" i wybór dnia (czytelna historia).
          Dół winiety gaśnie maską — nie koliduje z tekstem leadu w lewej kolumnie. */}
      <div ref={tabletRef} className="absolute -left-14 -top-24 z-0 hidden w-60 -rotate-3 opacity-90 will-change-transform xl:block">
        <div
          className="max-h-60 overflow-hidden"
          style={{
            maskImage: 'linear-gradient(180deg, #000 62%, transparent 96%)',
            WebkitMaskImage: 'linear-gradient(180deg, #000 62%, transparent 96%)',
          }}
        >
          <RezerwacjaVignette />
        </div>
      </div>
      {/* Desktop z grafikiem — scena główna */}
      <GrafikVignette className="relative z-10" />
      {/* Telefon pracownika — warstwa przednia */}
      <div ref={telefonRef} className="absolute -bottom-10 -right-3 z-20 w-36 rotate-1 will-change-transform sm:-right-6 sm:w-40">
        <TelefonPortfel />
      </div>
    </div>
  )
}
