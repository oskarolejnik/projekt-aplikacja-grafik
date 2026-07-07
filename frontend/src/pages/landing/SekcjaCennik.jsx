import { useState, useRef, useEffect } from 'react'
import { Icon } from '../../lib/icons'
import Porownywarka from './Porownywarka'
import { motionOn, reducedMotion, useParallax } from './motionPro'

// Cennik landingu „Lokalo Noir": gigantyczne słowo-tło (parallax) rozmywane szkłem kart,
// przełącznik okresu (szuflada iOS), karty planów z tiltem 3D i wodzącym światłem.
// TREŚĆ/CENY zachowane 1:1 (0/129/249/439 + Enterprise) — to jest cel konwersji strony.

const MAIL = 'mailto:kontakt@grafikpracy.pl'

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

const zl = (n) => n.toLocaleString('pl-PL')

function PriceNum({ value }) {
  const [disp, setDisp] = useState(value)
  const cur = useRef(value)
  const raf = useRef(0)
  useEffect(() => {
    if (value == null || reducedMotion()) { cur.current = value; setDisp(value); return }
    cancelAnimationFrame(raf.current)
    const a = cur.current == null ? value : cur.current
    const start = performance.now()
    const step = (t) => {
      const p = Math.min(1, (t - start) / 460)
      const eased = 1 - Math.pow(1 - p, 3)
      const v = Math.round(a + (value - a) * eased)
      cur.current = v; setDisp(v)
      if (p < 1) raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [value])
  return <>{value == null ? 'wycena' : zl(disp)}</>
}

function SzczegolyPlanu({ wiersze }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-5 border-t border-white/[0.06] pt-4">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 text-left text-sm font-semibold text-muted transition hover:text-ink">
        Dla kogo i co zyskujesz
        <Icon name="chevronDown" className={`h-4 w-4 shrink-0 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </button>
      <div className={`ck-faq ${open ? 'open' : ''}`}><div>
        <dl className="space-y-3 pt-4">
          {wiersze.map(([l, t]) => (
            <div key={l}>
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-zloto/80">{l}</dt>
              <dd className="mt-0.5 text-sm leading-relaxed text-muted">{t}</dd>
            </div>
          ))}
        </dl>
      </div></div>
    </div>
  )
}

export default function SekcjaCennik() {
  const [okres, setOkres] = useState('rok')
  const slowoRef = useRef(null)
  const glowne = CENNIK.filter((p) => p.mies != null && p.mies > 0)
  const boczne = CENNIK.filter((p) => p.mies === 0 || p.mies == null)
  useParallax(slowoRef, 0.12, motionOn())

  const anim = motionOn()
  const tiltMove = (e) => {
    const el = e.currentTarget, r = el.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height
    el.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`)
    el.style.setProperty('--my', `${(y * 100).toFixed(1)}%`)
    el.style.setProperty('--rx', `${((0.5 - y) * 3.5).toFixed(2)}deg`)
    el.style.setProperty('--ry', `${((x - 0.5) * 4.5).toFixed(2)}deg`)
  }
  const tiltReset = (e) => {
    e.currentTarget.style.setProperty('--rx', '0deg')
    e.currentTarget.style.setProperty('--ry', '0deg')
  }
  const statusRozliczenia = (p) => (okres === 'rok' && p.mies > p.rok)
    ? <>rozliczane rocznie · <span className="text-muted line-through">{zl(p.mies)} zł/mc</span></>
    : 'rozliczane co miesiąc'

  const Cecha = ({ dziecko, featured }) => {
    const tekst = typeof dziecko === 'string' ? dziecko : dziecko.t
    const nowe = typeof dziecko === 'object' && dziecko.nowe
    return (
      <li className="flex items-start gap-2.5 text-sm">
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
    <section id="cennik" className="ck-scope scroll-mt-20 py-20 sm:py-28">
      <style>{`
        .ck-scope { --e: cubic-bezier(.22,1,.36,1); }
        .ck-scope .glass { border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.03);
          backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 48px -24px rgba(0,0,0,0.55); }
        .ck-scope .glass:hover { border-color: rgba(255,255,255,0.16); background: rgba(255,255,255,0.055); }
        .ck-scope .tilt { transition: transform .25s var(--e), border-color .22s var(--e), background-color .22s var(--e), box-shadow .22s var(--e); transform-style: preserve-3d;
          transform: perspective(950px) rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg)) translateY(var(--ty,0)); }
        .ck-scope .tilt:hover { --ty: -5px; }
        .ck-scope .tilt::after { content:''; position:absolute; inset:0; border-radius:inherit; pointer-events:none; opacity:0; transition:opacity .35s var(--e);
          background: radial-gradient(26rem 26rem at var(--mx,50%) var(--my,50%), rgba(231,207,155,0.06), transparent 62%); }
        .ck-scope .tilt:hover::after { opacity:1; }
        .ck-scope .lift { transition: transform .22s var(--e), border-color .22s var(--e), background-color .22s var(--e); }
        .ck-scope .lift:hover { transform: translateY(-4px); }
        .ck-scope .ck-faq { display:grid; grid-template-rows:0fr; transition:grid-template-rows .32s var(--e); }
        .ck-scope .ck-faq.open { grid-template-rows:1fr; }
        .ck-scope .ck-faq > div { overflow:hidden; min-height:0; }
        @media (prefers-reduced-motion: reduce) { .ck-scope .tilt, .ck-scope .tilt:hover { transform:none !important; } .ck-scope .tilt::after { display:none; } .ck-scope .lift:hover { transform:none; } }
      `}</style>

      <div className="relative mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2 className="sr-only">Prosty cennik — płacisz za lokal, nie za osobę</h2>
        <div ref={slowoRef} aria-hidden className="pointer-events-none select-none will-change-transform">
          <div className="text-center font-brand text-[clamp(4rem,14vw,10.5rem)] font-bold leading-[0.85] tracking-tight text-ink/95">Cennik</div>
        </div>

        <div className="relative z-10 -mt-[clamp(0.9rem,3vw,2.1rem)] flex justify-center">
          <div className="relative inline-flex rounded-full border border-white/[0.08] bg-white/[0.05] p-1 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-xl">
            <span aria-hidden className="absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-full border border-white/[0.12] bg-white/[0.09] transition-transform duration-300 ease-drawer"
              style={{ transform: okres === 'rok' ? 'translateX(100%)' : 'translateX(0)' }} />
            {[['mies', 'Miesięcznie'], ['rok', 'Rocznie']].map(([k, l]) => (
              <button key={k} onClick={() => setOkres(k)} aria-pressed={okres === k}
                className={`relative z-10 flex min-h-11 min-w-[8.5rem] items-center justify-center gap-1.5 rounded-full px-4 py-2 font-semibold transition-colors duration-200 ${okres === k ? 'text-ink' : 'text-muted hover:text-ink'}`}>
                {l}
                {k === 'rok' && <span className="rounded-full bg-zloto/15 px-1.5 py-0.5 text-[10px] font-semibold text-zloto">−2 mies.</span>}
              </button>
            ))}
          </div>
        </div>

        <p className="relative z-10 mx-auto mt-5 flex max-w-xl items-center justify-center gap-2 text-center text-sm text-muted">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-zloto/25 bg-zloto/[0.08] px-3 py-1 text-xs font-semibold text-zloto">
            <span className="h-1.5 w-1.5 rounded-full bg-zloto" /> 14 dni za darmo
          </span>
          Każdy plan zaczyna od 14 dni pełnego Premium — bez karty.
        </p>

        <div className="relative z-10 mx-auto mt-10 grid max-w-5xl gap-5 lg:grid-cols-3 lg:items-stretch lg:gap-6 lg:pt-6">
          {glowne.map((p) => {
            const cena = okres === 'rok' ? p.rok : p.mies
            return (
              <article key={p.nazwa}
                onPointerMove={anim ? tiltMove : undefined} onPointerLeave={anim ? tiltReset : undefined}
                className={`glass tilt relative flex flex-col rounded-3xl p-6 sm:p-7 ${p.flagowy ? 'z-10 border-zloto/25 bg-white/[0.05] max-lg:-order-1 lg:-my-6 lg:px-8' : ''}`}>
                {p.flagowy && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-zloto px-3 py-1 text-[11px] font-semibold text-noc shadow-cta">Najczęściej wybierany</span>
                )}
                <h3 className="font-brand text-base font-semibold text-ink">{p.nazwa}</h3>
                <p className="mt-0.5 text-xs text-muted">{p.opis}</p>
                <div className="mt-5 flex items-baseline gap-1.5">
                  <span className={`font-brand font-bold tabular-nums tracking-tight text-ink ${p.flagowy ? 'text-5xl sm:text-6xl' : 'text-5xl'}`}><PriceNum value={cena} /></span>
                  <span className="text-sm text-muted">zł/mc</span>
                </div>
                <div className="mt-1.5 h-4 text-xs text-muted">{statusRozliczenia(p)}</div>
                <ul className="mt-6 flex-1 space-y-3 border-t border-white/[0.06] pt-6">
                  {p.cechy.map((c) => <Cecha key={typeof c === 'string' ? c : c.t} dziecko={c} featured={p.flagowy} />)}
                </ul>
                {p.szczegoly && <SzczegolyPlanu wiersze={p.szczegoly} />}
                <a href={`?start&plan=${p.nazwa.toLowerCase()}`}
                  className={`mt-6 rounded-xl px-4 py-3 text-center text-sm font-semibold transition duration-200 active:scale-[0.98] ${p.flagowy ? 'bg-zloto text-noc hover:bg-zloto-2' : 'border border-white/[0.10] bg-white/[0.04] text-ink hover:border-white/[0.16] hover:bg-white/[0.08]'}`}>
                  Wybieram {p.nazwa}
                </a>
              </article>
            )
          })}
        </div>

        <div className="relative z-10 mx-auto mt-6 grid max-w-5xl gap-5 sm:grid-cols-2 lg:gap-6">
          {boczne.map((p) => {
            const darmowy = p.mies === 0
            return (
              <article key={p.nazwa} className="glass lift flex flex-col justify-between gap-4 rounded-3xl p-6 sm:flex-row sm:items-center">
                <div className="min-w-0">
                  <div className="flex items-baseline gap-3">
                    <h3 className="font-brand text-base font-semibold text-ink">{p.nazwa}</h3>
                    <span className="font-brand text-xl font-bold tabular-nums text-ink">{darmowy ? '0 zł' : 'wycena'}</span>
                    <span className="text-xs text-muted">{darmowy ? 'na zawsze' : 'indywidualnie'}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted">{p.opis}</p>
                  <p className="mt-2 text-xs leading-relaxed text-muted/80">{p.cechy.map((c) => (typeof c === 'string' ? c : c.t)).join(' · ')}</p>
                </div>
                <a href={darmowy ? '?start&plan=darmowy' : `${MAIL}?subject=Enterprise`}
                  className={`shrink-0 rounded-xl px-5 py-2.5 text-center text-sm font-semibold transition duration-200 active:scale-[0.98] ${darmowy ? 'bg-mint text-bg hover:brightness-105' : 'border border-white/[0.10] bg-white/[0.04] text-ink hover:border-white/[0.16] hover:bg-white/[0.08]'}`}>
                  {darmowy ? 'Zacznij za darmo' : 'Zapytaj o wycenę'}
                </a>
              </article>
            )
          })}
        </div>

        <p className="relative z-10 mt-7 text-center text-xs text-muted">
          Ceny netto. Dodatek integracji POS: <span className="text-ink">+149 zł/mc</span>. Płacisz za lokal, nie za osobę.
          <span className="mt-1 block text-muted">Plan zmieniasz lub anulujesz w każdej chwili — moduły włączasz jednym kliknięciem.</span>
        </p>

        <Porownywarka />
      </div>
    </section>
  )
}
