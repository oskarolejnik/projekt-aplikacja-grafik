import { useRef } from 'react'
import { Logo } from '../components/Logo'
import { useLenisGsap, useReveal } from './landing/motionPro'
import HeroPro from './landing/HeroPro'
import PainRelief from './landing/PainRelief'
import ShowcasePinned from './landing/ShowcasePinned'
import SekcjaRole from './landing/SekcjaRole'
import SekcjaPlatformy from './landing/SekcjaPlatformy'
import SekcjaWhiteLabel from './landing/SekcjaWhiteLabel'
import SekcjaCennik from './landing/SekcjaCennik'
import SekcjaZaufanie from './landing/SekcjaZaufanie'
import SekcjaFinal from './landing/SekcjaFinal'

// Landing „Lokalo Noir" v4 — premium, scroll-storytelling (Lenis + GSAP + subtelne 3D).
// Rejestr BRAND: ciepła czerń (noc/wegiel) + złota nitka (zloto). Ekrany produktu w winietach
// mówią językiem produktu (mięta) — noir to rama sceny, nie treść.

const MAIL = 'mailto:kontakt@grafikpracy.pl'

export default function ProduktPro() {
  const root = useRef(null)
  useLenisGsap()
  useReveal(root)

  return (
    <div ref={root} className="relative min-h-dvh bg-noc font-switzer text-ink">
      {/* Statyczne złote światło sceny (≤5%) — jedyny „gradient", pod spodem 3D/treści. */}
      <div aria-hidden className="pointer-events-none fixed inset-0" style={{ background:
        'radial-gradient(64rem 42rem at 16% -8%, rgba(201,169,106,0.06), transparent 62%),' +
        'radial-gradient(48rem 32rem at 88% 4%, rgba(255,255,255,0.03), transparent 60%)' }} />

      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-noc/70 backdrop-blur-xl">
        <nav className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <a href="?produkt" className="flex items-center gap-2.5">
            <Logo className="h-8" variant="gradient" />
            <span className="font-brand text-lg font-bold">Lokalo</span>
          </a>
          <div className="hidden items-center gap-7 text-sm font-semibold text-muted md:flex">
            <a href="#mozliwosci" className="transition hover:text-ink">Możliwości</a>
            <a href="#role" className="transition hover:text-ink">Role</a>
            <a href="#cennik" className="transition hover:text-ink">Cennik</a>
            <a href="#faq" className="transition hover:text-ink">FAQ</a>
          </div>
          <div className="flex items-center gap-2.5">
            <a href="?login" className="rounded-xl px-3 py-2 text-sm font-semibold text-muted transition hover:text-ink">Zaloguj</a>
            <a href="#cennik" className="rounded-xl bg-zloto px-4 py-2 text-sm font-semibold text-noc transition hover:bg-zloto-2 active:scale-[0.98]">Wybierz pakiet</a>
          </div>
        </nav>
      </header>

      <main className="relative z-10">
        <HeroPro />
        <PainRelief />
        <ShowcasePinned />
        <SekcjaRole />
        <SekcjaPlatformy />
        <SekcjaWhiteLabel />
        <SekcjaCennik />
        <SekcjaZaufanie />
        <SekcjaFinal />
      </main>

      <footer className="relative z-10 border-t border-white/[0.06]">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-3 px-4 py-8 text-xs text-muted/70 sm:flex-row sm:px-6">
          <div className="flex items-center gap-2">
            <Logo className="h-6" variant="gradient" />
            <span className="font-brand font-bold text-muted">Lokalo</span>
          </div>
          <span>© Lokalo — oprogramowanie własnościowe. Wszelkie prawa zastrzeżone.</span>
        </div>
      </footer>
    </div>
  )
}
