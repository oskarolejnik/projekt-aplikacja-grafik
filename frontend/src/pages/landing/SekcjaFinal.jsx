import { useState } from 'react'
import { Icon } from '../../lib/icons'

// Domknięcie landingu: „Dla kogo" (segmenty rynku) + FAQ (rozwijane) + końcowe CTA.
// Treść zachowana z dotychczasowego landingu (przetestowana sprzedażowo).

const MAIL = 'mailto:kontakt@grafikpracy.pl'

const SEGMENTY = [
  ['sparkles', 'Domy weselne i lokale eventowe', 'Obsada per goście, zadatki, rozliczanie imprez i sal — czego nie robią zwykłe grafikówki ani POS.'],
  ['clipboard', 'Restauracje', 'Grafik + RCP → wypłaty, rozliczenie utargu i rezerwacje w jednym narzędziu.'],
  ['pin', 'Bary i puby', 'Szybki grafik, rozliczenia zmiany, rezerwacje stolików i lóż.'],
  ['clock', 'Kawiarnie i food trucki', 'Prosty grafik, dyspozycyjność i ewidencja czasu — start na planie darmowym.'],
]

const FAQ = [
  ['Muszę ręcznie przepisywać dane z Excela?', 'Nie na siłę. Zaczynasz od grafiku, resztę modułów włączasz, kiedy chcesz. Pracowników i kwalifikacje wprowadzasz raz — potem system pracuje za Ciebie.'],
  ['Działa na telefonie i bez internetu?', 'Tak. To aplikacja webowa (PWA) oraz natywna na iOS i Androida — instalujesz ją jak zwykłą apkę. Pracownik widzi swój grafik i zgłasza dyspozycyjność z telefonu.'],
  ['Co z RODO i bezpieczeństwem płac?', 'Dane wrażliwe są szyfrowane, dostęp do płac trafia do dziennika audytu, a role ograniczają, kto co widzi. Dla Enterprise dokładamy umowę powierzenia (DPA).'],
  ['Muszę mieć system POS?', 'Nie. POS to opcjonalny dodatek do rozliczeń „na żywo". Grafik, ewidencja czasu, wypłaty i rezerwacje działają bez niego.'],
  ['Ile trwa wdrożenie?', 'Konto stawiasz sam w kilka minut — kreator prowadzi krok po kroku. Przy Enterprise dokładamy dedykowany onboarding i migrację.'],
]

function FaqItem({ q, a }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-b border-white/[0.08]">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 py-4 text-left transition hover:text-ink">
        <span className="font-brand text-base font-semibold text-ink">{q}</span>
        <Icon name="chevronDown" className={`h-5 w-5 shrink-0 text-muted transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </button>
      <div className={`fn-faq ${open ? 'open' : ''}`}><div>
        <p className="pb-4 pr-8 text-sm leading-relaxed text-muted">{a}</p>
      </div></div>
    </div>
  )
}

export default function SekcjaFinal() {
  return (
    <div className="fn-scope relative mx-auto w-full max-w-6xl px-4 sm:px-6">
      <style>{`
        .fn-scope { --e: cubic-bezier(.22,1,.36,1); }
        .fn-scope .lift { transition: transform .22s var(--e), border-color .22s var(--e), background-color .22s var(--e); }
        .fn-scope .lift:hover { transform: translateY(-4px); }
        .fn-scope .fn-faq { display:grid; grid-template-rows:0fr; transition:grid-template-rows .32s var(--e); }
        .fn-scope .fn-faq.open { grid-template-rows:1fr; }
        .fn-scope .fn-faq > div { overflow:hidden; min-height:0; }
        @media (prefers-reduced-motion: reduce) { .fn-scope .lift:hover { transform:none; } }
      `}</style>

      <section className="py-14">
        <h2 data-head className="text-center font-brand text-2xl font-semibold sm:text-3xl">Dla kogo</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {SEGMENTY.map(([ico, t, o]) => (
            <div key={t} data-animate className="lift flex gap-3.5 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5">
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

      <section id="faq" className="scroll-mt-20 py-14">
        <h2 data-head className="text-center font-brand text-2xl font-semibold sm:text-3xl">Częste pytania</h2>
        <div data-animate className="mx-auto mt-8 max-w-2xl">
          {FAQ.map(([q, a]) => <FaqItem key={q} q={q} a={a} />)}
        </div>
      </section>

      <section data-animate className="my-14 overflow-hidden rounded-3xl border border-zloto/25 bg-wegiel p-10 text-center sm:p-14">
        <h2 className="mx-auto max-w-2xl font-brand text-3xl font-semibold sm:text-4xl" style={{ textWrap: 'balance' }}>
          Zbuduj <em className="font-editorial font-medium italic text-zloto-2">przewagę operacyjną</em> swojego lokalu.
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-base text-muted">Załóż konto w kilka minut albo umów demo — pokażemy, jak przenieść grafik, wypłaty i rezerwacje w jedno miejsce.</p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <a href="?start" className="rounded-xl bg-zloto px-7 py-3 text-sm font-semibold text-noc transition-colors hover:bg-zloto-2 active:scale-[0.98]">Zacznij za darmo</a>
          <a href={`${MAIL}?subject=Demo%20Lokalo`} className="rounded-xl border border-white/[0.12] px-7 py-3 text-sm font-semibold text-ink transition hover:bg-white/[0.06] active:scale-[0.98]">Umów demo</a>
        </div>
      </section>
    </div>
  )
}
