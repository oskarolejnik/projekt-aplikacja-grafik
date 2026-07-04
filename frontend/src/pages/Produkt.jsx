import { useState, useRef, useEffect } from 'react'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { useReveal, useSmoothAnchors, animacjeWlaczone, prefersReducedMotion } from './landing/motion'
import HeroEkosystem from './landing/HeroEkosystem'
import SekcjaPokazy from './landing/SekcjaPokazy'
import SekcjaRole from './landing/SekcjaRole'
import SekcjaPlatformy from './landing/SekcjaPlatformy'
import SekcjaWhiteLabel from './landing/SekcjaWhiteLabel'
import SekcjaZaufanie from './landing/SekcjaZaufanie'
import Porownywarka from './landing/Porownywarka'

// Publiczny landing sprzedażowy „Lokalo". Renderowany pod ?produkt ORAZ jako publiczne /
// dla niezalogowanego gościa (App.jsx). Bez kontekstów instancji — działa samodzielnie.
// Rejestr BRAND „Lokalo Noir" (DESIGN.md §8): ciepła czerń + złota nitka; ekrany produktu
// w winietach mówią językiem produktu (Cicha scena, mięta) — noir to rama, nie treść.

const MAIL = 'mailto:kontakt@grafikpracy.pl'

// Cecha planu: string albo { t, nowe: true } — „nowość" dostaje chip (świeżość produktu sprzedaje).
// `szczegoly` — rozwijana architektura wartości planu: dla kogo, scenariusz, rachunek, role, automatyzacja.
const CENNIK = [
  { nazwa: 'Darmowy', mies: 0, rok: 0, opis: '1 lokal, do ~8 osób', cechy: [
    'Grafik + dyspozycyjność zespołu', 'Publikacja grafiku + role i uprawnienia',
    'Giełda wymiany zmian', 'Powiadomienia push', 'Aplikacja na telefon (PWA)'] },
  { nazwa: 'Basic', mies: 129, rok: 99, opis: '1 lokal, bez limitu osób', cechy: [
    'Wszystko z Darmowego', 'Ewidencja czasu pracy (RCP)',
    'Raporty godzin → wypłaty co do minuty', 'Eksport wypłat do Excela dla księgowej',
    { t: 'Portfel pracownika: zarobki na żywo + zaliczki', nowe: true },
    'Strażnik prawa pracy (odpoczynek, limity dni)'],
    szczegoly: [
      ['Dla kogo', 'Kawiarnia, bistro, pub z zespołem 5–15 osób rozliczanym godzinowo.'],
      ['Scenariusz', 'Koniec miesiąca bez kalkulatora: odbicia RCP spinają się z grafikiem i stawkami, a księgowa dostaje gotowy eksport.'],
      ['Rachunek wartości', '2–3 godziny liczenia wypłat i jeden błąd stawki miesięcznie kosztują więcej niż abonament.'],
      ['Role w cenie', 'Właściciel, manager i pracownicy — każdy z własnym widokiem godzin i portfela.'],
      ['Automatyzacja', 'Wypłaty, strażnik prawa pracy i powiadomienia liczą się same; grafik układasz Ty.'],
    ] },
  { nazwa: 'Pro', mies: 249, rok: 199, flagowy: true, opis: 'Standard dla restauracji', cechy: [
    'Wszystko z Basic', 'Rozliczenia kasowe dnia + zeszyt kasowy',
    'Alerty anomalii kasowych', 'Rezerwacje stolików + interaktywny plan sali',
    'CRM gości ze scoringiem no-show', 'Pulpit KPI + prognoza ruchu i obsady',
    { t: 'Zgodność: badania sanepid + terminy lokalu', nowe: true }],
    szczegoly: [
      ['Dla kogo', 'Restauracja z rezerwacjami i kasą, 15–40 osób na zmianach, manager na etacie.'],
      ['Scenariusz', 'Piątkowy wieczór: rezerwacje spływają same, rozliczenie dnia zgadza się z kasą, a różnice podświetlają się, zanim urosną.'],
      ['Rachunek wartości', 'Jedna wychwycona różnica kasowa tygodniowo i pełny obraz kosztu pracy zwykle pokrywają abonament z nawiązką.'],
      ['Role w cenie', 'Wszystkie z Basic + szef kuchni, bar i kasa z rozliczeniem dnia.'],
      ['Automatyzacja', 'Auto-grafik z kwalifikacji, prognoza ruchu i obsady, alerty kasowe — system podpowiada, Ty zatwierdzasz.'],
    ] },
  { nazwa: 'Premium', mies: 439, rok: 349, opis: 'Domy weselne i eventowe', cechy: [
    'Wszystko z Pro', 'Imprezy i wesela + zadatki z kasy',
    { t: 'Skrzynka zapytań o imprezy (AI)', nowe: true },
    { t: 'Portal Pary Młodej: goście, menu, wpłaty', nowe: true },
    'Rezerwacje online bez prowizji', 'Napiwki: uczciwy podział puli',
    'White-label — Twoja marka i logo'],
    szczegoly: [
      ['Dla kogo', 'Dom weselny, lokal eventowy, restauracja z salami — imprezy to istotny przychód.'],
      ['Scenariusz', 'Zapytanie o wesele: AI szykuje szkic odpowiedzi z ofertą, zadatek spina się z kasą, a Para Młoda prowadzi listę gości we własnym portalu.'],
      ['Rachunek wartości', 'Jedna szybciej domknięta impreza w miesiącu to wielokrotność abonamentu — odpowiadasz w minuty, nie w dni.'],
      ['Role w cenie', 'Wszystkie z Pro + portal gościa (Para Młoda) i white-label dla Twojej marki.'],
      ['Automatyzacja', 'Najwyższa: szkice ofert AI, raty zadatków, rezerwacje online i podział napiwków liczą się same.'],
    ] },
  { nazwa: 'Enterprise', mies: null, rok: null, opis: 'Sieci i franczyzy', cechy: [
    'Multi-lokal i konsolidacja raportów', 'SSO + panel super-admina',
    'Antyfraud POS: storna per kelner', 'SLA + umowa powierzenia (DPA)',
    'Dedykowany onboarding i migracja'] },
]

const SEGMENTY = [
  ['sparkles', 'Domy weselne i lokale eventowe', 'Obsada per goście, zadatki, rozliczanie imprez i sal — czego nie robią zwykłe grafikówki ani POS.'],
  ['clipboard', 'Restauracje', 'Grafik + RCP → wypłaty, rozliczenie utargu i rezerwacje w jednym narzędziu.'],
  ['pin', 'Bary i puby', 'Szybki grafik, rozliczenia zmiany, rezerwacje stolików i lóż.'],
  ['clock', 'Kawiarnie i food trucki', 'Prosty grafik, dyspozycyjność i ewidencja czasu — start na planie darmowym.'],
]

const FAQ = [
  ['Muszę ręcznie przepisywać dane z Excela?', 'Nie na siłę. Zaczynasz od grafiku, resztę modułów włączasz, kiedy chcesz. Pracowników i kwalifikacje wprowadzasz raz — potem system pracuje za Ciebie.'],
  ['Działa na telefonie i bez internetu?', 'Tak. To aplikacja webowa (PWA) — instalujesz ją jak zwykłą apkę na telefonie i desktopie. Pracownik widzi swój grafik i zgłasza dyspozycyjność z telefonu.'],
  ['Co z RODO i bezpieczeństwem płac?', 'Dane wrażliwe są szyfrowane, dostęp do płac trafia do dziennika audytu, a role ograniczają, kto co widzi. Dla Enterprise dokładamy umowę powierzenia (DPA).'],
  ['Muszę mieć system POS?', 'Nie. POS to opcjonalny dodatek do rozliczeń „na żywo". Grafik, ewidencja czasu, wypłaty i rezerwacje działają bez niego.'],
  ['Ile trwa wdrożenie?', 'Konto stawiasz sam w kilka minut — kreator prowadzi krok po kroku. Przy Enterprise dokładamy dedykowany onboarding i migrację.'],
]

const zl = (n) => n.toLocaleString('pl-PL')

// Magnetyczne CTA: przycisk lekko podąża za kursorem (≤ ~7px), wraca po zejściu.
// Czysty transform ze zmiennych CSS — zero re-renderów; reduced-motion → wyłączone.
function Magnes({ href, className = '', children }) {
  const anim = animacjeWlaczone()
  const move = (e) => {
    const el = e.currentTarget
    const r = el.getBoundingClientRect()
    el.style.setProperty('--tx', `${((e.clientX - r.left - r.width / 2) * 0.14).toFixed(1)}px`)
    el.style.setProperty('--ty', `${((e.clientY - r.top - r.height / 2) * 0.22).toFixed(1)}px`)
  }
  const leave = (e) => {
    e.currentTarget.style.setProperty('--tx', '0px')
    e.currentTarget.style.setProperty('--ty', '0px')
  }
  return (
    <a href={href} onPointerMove={anim ? move : undefined} onPointerLeave={anim ? leave : undefined} className={`magnes ${className}`}>
      {children}
    </a>
  )
}

// Animowana liczba ceny (odliczanie przy zmianie okresu). Reduced-motion → skok.
function PriceNum({ value }) {
  const [disp, setDisp] = useState(value)
  const cur = useRef(value)
  const raf = useRef(0)
  useEffect(() => {
    if (value == null || prefersReducedMotion()) { cur.current = value; setDisp(value); return }
    cancelAnimationFrame(raf.current)
    const a = cur.current == null ? value : cur.current
    const start = performance.now()
    const step = (t) => {
      const p = Math.min(1, (t - start) / 460)
      const eased = 1 - Math.pow(1 - p, 3)
      const v = Math.round(a + (value - a) * eased)
      cur.current = v
      setDisp(v)
      if (p < 1) raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [value])
  return <>{value == null ? 'wycena' : zl(disp)}</>
}

// Rozwijane szczegóły planu (dla kogo / scenariusz / rachunek / role / automatyzacja).
function SzczegolyPlanu({ wiersze }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-5 border-t border-white/[0.06] pt-4">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 text-left text-sm font-semibold text-muted transition hover:text-ink"
      >
        Dla kogo i co zyskujesz
        <Icon name="chevronDown" className={`h-4 w-4 shrink-0 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </button>
      <div className={`faq-body ${open ? 'open' : ''}`}>
        <div>
          <dl className="space-y-3 pt-4">
            {wiersze.map(([l, t]) => (
              <div key={l}>
                <dt className="text-[11px] font-semibold uppercase tracking-wider text-zloto/80">{l}</dt>
                <dd className="mt-0.5 text-sm leading-relaxed text-muted">{t}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  )
}

function Cennik() {
  const [okres, setOkres] = useState('rok') // 'mies' | 'rok'
  const slowoRef = useRef(null)
  const glowne = CENNIK.filter((p) => p.mies != null && p.mies > 0)          // Basic · Pro · Premium
  const boczne = CENNIK.filter((p) => p.mies === 0 || p.mies == null)        // Darmowy · Enterprise

  // Paralaksa gigantycznego słowa: przy scrollu płynie wolniej niż treść (głębia sceny).
  // POMIAR na wrapperze (nietransformowanym), TRANSFORM na dziecku — inaczej rect liczyłby
  // pozycję już po przesunięciu i offset narastałby w pętli sprzężenia zwrotnego.
  const slowoWrapRef = useRef(null)
  useEffect(() => {
    if (!animacjeWlaczone()) return
    let raf = 0
    const tick = () => {
      raf = 0
      const wrap = slowoWrapRef.current
      const el = slowoRef.current
      if (!wrap || !el) return
      const r = wrap.getBoundingClientRect()
      const odCentrum = r.top + r.height / 2 - window.innerHeight / 2
      el.style.transform = `translateY(${(-odCentrum * 0.12).toFixed(1)}px)`
    }
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(tick) }
    // capture:true — na tej stronie przewija się BODY (overflow-x:hidden + height:100%
    // czyni go scroll-kontenerem), a zdarzenie scroll nie bąbelkuje; capture łapie każdy scroller.
    window.addEventListener('scroll', onScroll, { passive: true, capture: true })
    tick()
    return () => { window.removeEventListener('scroll', onScroll, { capture: true }); if (raf) cancelAnimationFrame(raf) }
  }, [])

  // Tilt 3D + wodzące światło na kartach głównych: kursor ustawia zmienne CSS (rotacja ≤2.5°,
  // radialne światło w punkcie wskaźnika). Transform-only, zero re-renderów Reacta.
  const anim = animacjeWlaczone()
  const tiltMove = (e) => {
    const el = e.currentTarget
    const r = el.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width
    const y = (e.clientY - r.top) / r.height
    el.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`)
    el.style.setProperty('--my', `${(y * 100).toFixed(1)}%`)
    el.style.setProperty('--rx', `${((0.5 - y) * 3.5).toFixed(2)}deg`)
    el.style.setProperty('--ry', `${((x - 0.5) * 4.5).toFixed(2)}deg`)
  }
  const tiltReset = (e) => {
    const el = e.currentTarget
    el.style.setProperty('--rx', '0deg')
    el.style.setProperty('--ry', '0deg')
  }

  const statusRozliczenia = (p) => {
    const oszczedza = okres === 'rok' && p.mies > p.rok
    return oszczedza
      ? <>rozliczane rocznie · <span className="text-muted/60 line-through">{zl(p.mies)} zł/mc</span></>
      : 'rozliczane co miesiąc'
  }

  const Cecha = ({ dziecko, featured, j }) => {
    const tekst = typeof dziecko === 'string' ? dziecko : dziecko.t
    const nowe = typeof dziecko === 'object' && dziecko.nowe
    return (
      <li className="cecha flex items-start gap-2.5 text-sm" style={{ '--j': j }}>
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/[0.07]">
          <Icon name="check" className={`h-3 w-3 ${featured ? 'text-zloto' : 'text-ink'}`} />
        </span>
        <span className="leading-snug text-muted">
          {tekst}
          {nowe && <span className="ml-1.5 inline-block rounded-full bg-mint/15 px-1.5 py-0.5 align-middle text-[10px] font-semibold leading-none text-mint">nowość</span>}
        </span>
      </li>
    )
  }

  return (
    <div className="relative">
      {/* Gigantyczne słowo-tło: karty szkła rozmywają je swoim backdrop-blur — kino, nie dekoracja-tapeta.
          Czysto wizualne (aria-hidden); tytuł sekcji niesie <h2 class="sr-only"> we wrapperze. */}
      <div ref={slowoWrapRef} aria-hidden className="pointer-events-none select-none">
        <div
          ref={slowoRef}
          className="text-center font-brand text-[clamp(4rem,14vw,10.5rem)] font-bold leading-[0.85] tracking-tight text-ink will-change-transform"
        >
          Cennik
        </div>
      </div>

      {/* Przełącznik okresu — szklana pigułka z przesuwnym kciukiem (krzywa szuflady iOS). */}
      <div data-rv="" className="relative z-10 -mt-[clamp(0.9rem,3vw,2.1rem)] flex justify-center">
        <div className="relative inline-flex rounded-full border border-white/[0.08] bg-white/[0.05] p-1 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-xl">
          <span
            aria-hidden
            className="absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-full border border-white/[0.12] bg-white/[0.09] transition-transform duration-300 ease-drawer"
            style={{ transform: okres === 'rok' ? 'translateX(100%)' : 'translateX(0)' }}
          />
          {[['mies', 'Miesięcznie'], ['rok', 'Rocznie']].map(([k, l]) => (
            <button
              key={k}
              onClick={() => setOkres(k)}
              aria-pressed={okres === k}
              className={`relative z-10 flex min-w-[8.5rem] items-center justify-center gap-1.5 rounded-full px-4 py-2 font-semibold transition-colors duration-200 ${okres === k ? 'text-ink' : 'text-muted hover:text-ink'}`}
            >
              {l}
              {k === 'rok' && <span className="rounded-full bg-zloto/15 px-1.5 py-0.5 text-[10px] font-semibold text-zloto">−2 mies.</span>}
            </button>
          ))}
        </div>
      </div>

      {/* Trzy plany główne — pływające szkło; flagowy Pro uniesiony, ze złotym CTA. */}
      <div className="relative z-10 mx-auto mt-10 grid max-w-5xl gap-5 lg:grid-cols-3 lg:items-stretch lg:gap-6 lg:pt-6">
        {glowne.map((p, idx) => {
          const cena = okres === 'rok' ? p.rok : p.mies
          return (
            <article
              key={p.nazwa}
              data-rv=""
              style={{ '--i': idx }}
              onPointerMove={anim ? tiltMove : undefined}
              onPointerLeave={anim ? tiltReset : undefined}
              className={`glass tilt rv-scale relative flex flex-col rounded-3xl p-6 sm:p-7 ${
                p.flagowy ? 'z-10 border-zloto/25 bg-white/[0.05] max-lg:-order-1 lg:-my-6 lg:px-8' : ''
              }`}
            >
              {p.flagowy && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-zloto px-3 py-1 text-[11px] font-semibold text-noc shadow-cta">
                  Najczęściej wybierany
                </span>
              )}
              <h3 className="font-brand text-base font-semibold text-ink">{p.nazwa}</h3>
              <p className="mt-0.5 text-xs text-muted">{p.opis}</p>

              <div className="mt-5 flex items-baseline gap-1.5">
                <span className={`font-brand font-bold tabular-nums tracking-tight text-ink ${p.flagowy ? 'text-5xl sm:text-6xl' : 'text-5xl'}`}>
                  <PriceNum value={cena} />
                </span>
                <span className="text-sm text-muted">zł/mc</span>
              </div>
              <div className="mt-1.5 h-4 text-xs text-muted">{statusRozliczenia(p)}</div>

              <ul className="mt-6 flex-1 space-y-3 border-t border-white/[0.06] pt-6">
                {p.cechy.map((c, j) => <Cecha key={typeof c === 'string' ? c : c.t} dziecko={c} featured={p.flagowy} j={j} />)}
              </ul>

              {p.szczegoly && <SzczegolyPlanu wiersze={p.szczegoly} />}

              {/* Wybór pakietu prowadzi do KREATORA lokalu (nie mailto) — plan
                  wędruje w URL i ustawia tier subskrypcji po założeniu konta. */}
              <a
                href={`?start&plan=${p.nazwa.toLowerCase()}`}
                className={`mt-6 rounded-xl px-4 py-3 text-center text-sm font-semibold transition duration-200 active:scale-[0.98] ${
                  p.flagowy
                    ? 'bg-zloto text-noc hover:bg-zloto-2'
                    : 'border border-white/[0.10] bg-white/[0.04] text-ink hover:border-white/[0.16] hover:bg-white/[0.08]'
                }`}
              >
                Wybieram {p.nazwa}
              </a>
            </article>
          )
        })}
      </div>

      {/* Skrzydła: wejście bez ryzyka (Darmowy) i wyjście w skalę (Enterprise) — celowo ciszej. */}
      <div className="relative z-10 mx-auto mt-6 grid max-w-5xl gap-5 sm:grid-cols-2 lg:gap-6">
        {boczne.map((p, idx) => {
          const darmowy = p.mies === 0
          return (
            <article
              key={p.nazwa}
              data-rv=""
              style={{ '--i': idx + 3 }}
              className="glass lift rv-scale flex flex-col justify-between gap-4 rounded-3xl p-6 sm:flex-row sm:items-center"
            >
              <div className="min-w-0">
                <div className="flex items-baseline gap-3">
                  <h3 className="font-brand text-base font-semibold text-ink">{p.nazwa}</h3>
                  <span className="font-brand text-xl font-bold tabular-nums text-ink">
                    {darmowy ? '0 zł' : 'wycena'}
                  </span>
                  <span className="text-xs text-muted">{darmowy ? 'na zawsze' : 'indywidualnie'}</span>
                </div>
                <p className="mt-0.5 text-xs text-muted">{p.opis}</p>
                <p className="mt-2 text-xs leading-relaxed text-muted/80">
                  {p.cechy.map((c) => (typeof c === 'string' ? c : c.t)).join(' · ')}
                </p>
              </div>
              <a
                href={darmowy ? '?start&plan=darmowy' : `${MAIL}?subject=Enterprise`}
                className={`shrink-0 rounded-xl px-5 py-2.5 text-center text-sm font-semibold transition duration-200 active:scale-[0.98] ${
                  darmowy
                    ? 'bg-mint text-bg hover:brightness-105'
                    : 'border border-white/[0.10] bg-white/[0.04] text-ink hover:border-white/[0.16] hover:bg-white/[0.08]'
                }`}
              >
                {darmowy ? 'Zacznij za darmo' : 'Zapytaj o wycenę'}
              </a>
            </article>
          )
        })}
      </div>

      <p className="relative z-10 mt-7 text-center text-xs text-muted">
        Ceny netto. Dodatek integracji POS: <span className="text-ink">+149 zł/mc</span>. Płacisz za lokal, nie za osobę.
        <span className="mt-1 block text-muted/70">Plan zmieniasz lub anulujesz w każdej chwili — moduły włączasz jednym kliknięciem.</span>
      </p>

      <Porownywarka />
    </div>
  )
}

function FaqItem({ q, a }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-white/[0.08]">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 py-4 text-left transition hover:text-ink"
      >
        <span className="font-brand text-base font-semibold text-ink">{q}</span>
        <Icon name="chevronDown" className={`h-5 w-5 shrink-0 text-muted transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </button>
      <div className={`faq-body ${open ? 'open' : ''}`}>
        <div>
          <p className="pb-4 pr-8 text-sm leading-relaxed text-muted">{a}</p>
        </div>
      </div>
    </div>
  )
}

export default function Produkt() {
  const root = useRef(null)
  useReveal(root)
  useSmoothAnchors()
  const anim = animacjeWlaczone()

  return (
    <div ref={root} data-anim={anim ? 'on' : undefined} className="lp relative min-h-dvh bg-noc font-switzer text-ink">
      <div aria-hidden className="swiatlo-noir pointer-events-none fixed inset-0" />
      <style>{`
        .lp { --e: cubic-bezier(.22,1,.36,1); }
        /* Światło sceny noir: ciepły, statyczny poblask złota (≤5%) + zimna kontra — nie gradient marki. */
        .lp .swiatlo-noir { background:
          radial-gradient(64rem 42rem at 16% -8%, rgba(201,169,106,0.05), transparent 62%),
          radial-gradient(48rem 32rem at 88% 4%, rgba(255,255,255,0.03), transparent 60%); }
        .lp [data-rv] { opacity: 1; }
        .lp[data-anim="on"] [data-rv] { opacity: 0; transform: translateY(30px); transition: opacity .6s var(--e), transform .6s var(--e); transition-delay: calc(var(--i,0) * 80ms); }
        .lp[data-anim="on"] [data-rv].rv-l { transform: translateX(-42px); }
        .lp[data-anim="on"] [data-rv].rv-r { transform: translateX(42px); }
        .lp[data-anim="on"] [data-rv].rv-scale { transform: translateY(22px) scale(.965); }
        .lp[data-anim="on"] [data-rv].in { opacity: 1; transform: none; }
        .lp .lift { transition: transform .22s var(--e), border-color .22s var(--e), box-shadow .22s var(--e), background-color .22s var(--e); }
        .lp .lift:hover { transform: translateY(-4px); }
        /* Szkło noir: monochromatyczne, rozmywa scenę pod spodem.
           Wierzchnia kreska światła = wewnętrzny cień 1px (nie gradient). */
        .lp .glass { border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.03);
          backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 48px -24px rgba(0,0,0,0.55); }
        .lp .glass:hover { border-color: rgba(255,255,255,0.16); background: rgba(255,255,255,0.055);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.09), 0 32px 60px -24px rgba(0,0,0,0.55); }
        /* Tilt 3D kart: rotacja ze zmiennych CSS ustawianych kursorem (≤2.5°),
           uniesienie na hover w tym samym transformie (bez konfliktu z reveal). */
        .lp .tilt { transition: transform .25s var(--e), border-color .22s var(--e),
          background-color .22s var(--e), box-shadow .22s var(--e); transform-style: preserve-3d; }
        .lp[data-anim="on"] [data-rv].tilt.in, .lp:not([data-anim="on"]) .tilt {
          transform: perspective(950px) rotateX(var(--rx, 0deg)) rotateY(var(--ry, 0deg)) translateY(var(--ty, 0)); }
        .lp .tilt:hover { --ty: -5px; }
        /* Wodzące światło: radialny rozbłysk w punkcie kursora — na noir lekko złoty. */
        .lp .tilt::after { content: ''; position: absolute; inset: 0; border-radius: inherit;
          pointer-events: none; opacity: 0; transition: opacity .35s var(--e);
          background: radial-gradient(26rem 26rem at var(--mx, 50%) var(--my, 50%), rgba(231,207,155,0.05), transparent 62%); }
        .lp .tilt:hover::after { opacity: 1; }
        /* Kaskada cech: po wylądowaniu karty (.in) wiersze wjeżdżają kolejno z lewej. */
        .lp[data-anim="on"] .glass .cecha { opacity: 0; transform: translateX(-8px);
          transition: opacity .5s var(--e), transform .5s var(--e);
          transition-delay: calc(180ms + var(--j, 0) * 55ms); }
        .lp[data-anim="on"] .glass.in .cecha { opacity: 1; transform: none; }
        /* Magnetyczne CTA: podąża za kursorem przez zmienne CSS; leniwa transition = miękki magnes. */
        .lp .magnes { transform: translate(var(--tx, 0px), var(--ty, 0px)); transition: transform .35s var(--e); will-change: transform; }
        .lp .faq-body { display: grid; grid-template-rows: 0fr; transition: grid-template-rows .32s var(--e); }
        .lp .faq-body.open { grid-template-rows: 1fr; }
        .lp .faq-body > div { overflow: hidden; min-height: 0; }
        @media (prefers-reduced-motion: reduce) {
          .lp[data-anim="on"] [data-rv] { opacity: 1 !important; transform: none !important; transition: none !important; }
          .lp .lift:hover { transform: none; }
          .lp .tilt, .lp .tilt:hover { transform: none !important; }
          .lp .tilt::after { display: none; }
          .lp .magnes { transform: none !important; transition: none !important; }
          .lp[data-anim="on"] .glass .cecha { opacity: 1 !important; transform: none !important; transition: none !important; }
        }
      `}</style>

      {/* Nawigacja */}
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

      <main className="relative z-10 mx-auto w-full max-w-6xl px-4 sm:px-6">
        {/* Hero — opowieść + ekosystem urządzeń */}
        <section className="grid items-center gap-12 py-14 lg:grid-cols-[1.05fr_1fr] lg:gap-10 lg:py-24">
          <div>
            {/* Początek celowo cichy: zero złota poza jednym CTA — kolor wchodzi dopiero niżej. */}
            <p data-rv="" style={{ '--i': 0 }} className="inline-flex items-center gap-2 rounded-full border border-white/[0.10] bg-white/[0.03] px-3 py-1 text-xs font-semibold text-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-white/40" /> System operacyjny lokalu gastronomicznego
            </p>
            <h1 data-rv="" style={{ '--i': 1 }} className="mt-5 font-brand text-4xl font-bold leading-[1.04] tracking-tight sm:text-5xl lg:text-6xl">
              Cały lokal w jednym systemie.
              <span className="block text-muted">Zamiast Excela, papieru i pięciu apek.</span>
            </h1>
            <p data-rv="" style={{ '--i': 2 }} className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
              Piątek, 19:40 — pełna sala. Grafik ułożony, kasa się zgadza, rezerwacje potwierdzają się
              same, a każdy z zespołu wie, gdzie ma być. Lokalo prowadzi operacje. Ty prowadzisz lokal.
            </p>
            <div data-rv="" style={{ '--i': 3 }} className="mt-8 flex flex-wrap gap-3">
              <Magnes href="?start" className="rounded-xl bg-zloto px-6 py-3 text-sm font-semibold text-noc transition-colors hover:bg-zloto-2">Zacznij za darmo</Magnes>
              <a href={`${MAIL}?subject=Demo%20Lokalo`} className="rounded-xl border border-white/[0.12] px-6 py-3 text-sm font-semibold text-ink transition hover:bg-white/[0.06] active:scale-[0.98]">Umów demo</a>
            </div>
            <p data-rv="" style={{ '--i': 4 }} className="mt-5 text-xs text-muted">Plan darmowy bez karty · start w kilka minut · telefon, tablet i desktop</p>
          </div>

          <div data-rv="" style={{ '--i': 2 }} className="rv-r">
            <HeroEkosystem />
          </div>
        </section>

        {/* Ból → rozwiązanie */}
        <section data-rv="" className="rv-scale my-8 rounded-3xl border border-white/[0.08] bg-white/[0.02] px-6 py-10 text-center sm:px-10">
          <h2 className="mx-auto max-w-2xl font-brand text-2xl font-semibold sm:text-3xl" style={{ textWrap: 'balance' }}>
            Grafik w niedzielny wieczór. Wypłaty na kalkulatorze. Rezerwacje na trzech kartkach.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-base text-muted">
            <em className="font-editorial italic text-zloto-2">To znika.</em> Jeden system prowadzi obieg całego lokalu — a Ty zajmujesz się gośćmi.
          </p>
        </section>
      </main>

      {/* Sekcje pełnej szerokości (własne kontenery w środku) */}
      <div className="relative z-10">
        <SekcjaPokazy />
        <SekcjaRole />
        <SekcjaPlatformy />
        <SekcjaWhiteLabel />
      </div>

      <main className="relative z-10 mx-auto w-full max-w-6xl px-4 sm:px-6">
        {/* Cennik + porównywarka */}
        <section id="cennik" className="scroll-mt-20 py-16 sm:py-24">
          <h2 className="sr-only">Prosty cennik — płacisz za lokal, nie za osobę</h2>
          <p data-rv="" style={{ '--i': 1 }} className="mx-auto mt-3 max-w-xl text-center text-base text-muted">Zacznij za darmo. Rośnij, kiedy chcesz — moduły włączasz jednym kliknięciem.</p>
          <Cennik />
        </section>
      </main>

      <div className="relative z-10">
        <SekcjaZaufanie />
      </div>

      <main className="relative z-10 mx-auto w-full max-w-6xl px-4 sm:px-6">
        {/* Dla kogo */}
        <section className="py-12">
          <h2 data-rv="" className="text-center font-brand text-2xl font-semibold sm:text-3xl">Dla kogo</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {SEGMENTY.map(([ico, t, o], i) => (
              <div key={t} data-rv="" style={{ '--i': i % 2 }} className="lift flex gap-3.5 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/[0.06] text-zloto">
                  <Icon name={ico} className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-brand text-base font-semibold text-ink">{t}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{o}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="scroll-mt-20 py-14">
          <h2 data-rv="" className="text-center font-brand text-2xl font-semibold sm:text-3xl">Częste pytania</h2>
          <div data-rv="" style={{ '--i': 1 }} className="mx-auto mt-8 max-w-2xl">
            {FAQ.map(([q, a]) => <FaqItem key={q} q={q} a={a} />)}
          </div>
        </section>

        {/* CTA końcowe */}
        <section data-rv="" className="rv-scale my-14 overflow-hidden rounded-3xl border border-zloto/25 bg-wegiel p-10 text-center sm:p-14">
          <h2 className="mx-auto max-w-2xl font-brand text-3xl font-semibold sm:text-4xl" style={{ textWrap: 'balance' }}>
            Zbuduj <em className="font-editorial font-medium italic text-zloto-2">przewagę operacyjną</em> swojego lokalu.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-base text-muted">Załóż konto w kilka minut albo umów demo — pokażemy, jak przenieść grafik, wypłaty i rezerwacje w jedno miejsce.</p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Magnes href="?start" className="rounded-xl bg-zloto px-7 py-3 text-sm font-semibold text-noc transition-colors hover:bg-zloto-2">Zacznij za darmo</Magnes>
            <a href={`${MAIL}?subject=Demo%20Lokalo`} className="rounded-xl border border-white/[0.12] px-7 py-3 text-sm font-semibold text-ink transition hover:bg-white/[0.06] active:scale-[0.98]">Umów demo</a>
          </div>
        </section>
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
