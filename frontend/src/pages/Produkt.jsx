import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'

// Publiczna strona produktu (marketing + cennik). Renderowana pod ?produkt, POZA aplikacją
// instancji (bez logowania, bez brandingu klienta). Fundament lejka sprzedaży (Rec#8 audytu).

const FEATURES = [
  ['calendar', 'Auto-grafik + dyspozycyjność', 'Algorytm układa zmiany z kwalifikacji, dostępności i urlopów. Koniec Excela i błędów obsady.'],
  ['clock', 'Ewidencja czasu → wypłaty', 'Godziny z RCP/POS spięte z grafikiem i stawkami. Dokładne naliczanie, mniej sporów.'],
  ['clipboard', 'Rozliczenia kasowe dnia', 'Utarg „1:1" z zeszytu: gotówka, karty, terminale, kasy, zadatki. Alerty anomalii.'],
  ['users', 'Rezerwacje + widget online', 'Własny kanał rezerwacji bez prowizji portali. Potwierdzenia e-mail, lista oczekujących.'],
  ['sparkles', 'Imprezy i wesela + zadatki', 'Kalendarz wydarzeń, obsada per liczba gości, zadatki z POS, rozliczanie imprez.'],
  ['key', 'White-label + role (RBAC)', 'Twoja marka, włączasz tylko potrzebne moduły. Granularne uprawnienia i prywatność danych.'],
]

const CENNIK = [
  { nazwa: 'Darmowy', cena: '0', opis: '1 lokal, do ~8 pracowników', cechy: ['Grafik + dyspozycyjność', 'Publikacja grafiku + role', 'Powiadomienia push'] },
  { nazwa: 'Basic', cena: '99', opis: '1 lokal, bez limitu osób', cechy: ['Wszystko z Darmowego', 'Ewidencja czasu (RCP)', 'Raporty godzin → wypłaty'] },
  { nazwa: 'Pro', cena: '199', opis: 'Standard dla restauracji', flagowy: true, cechy: ['Wszystko z Basic', 'Rozliczenia kasowe dnia', 'Rezerwacje stolików', 'Alerty + pulpit KPI'] },
  { nazwa: 'Premium', cena: '349', opis: 'Dla domów weselnych / eventowych', cechy: ['Wszystko z Pro', 'Imprezy/wesela + zadatki', 'Widget rezerwacji online', 'White-label'] },
  { nazwa: 'Enterprise', cena: 'wycena', opis: 'Sieci i franczyzy', cechy: ['Multi-lokal + konsolidacja', 'Panel super-admina + SSO', 'SLA + umowa DPA', 'Dedykowany onboarding'] },
]

const SEGMENTY = [
  ['Domy weselne i lokale eventowe', 'Obsada per goście, zadatki, rozliczanie imprez, sale — czego nie robią zwykłe grafikówki ani POS.'],
  ['Restauracje', 'Grafik + RCP → wypłaty + rozliczenie utargu + rezerwacje w jednym narzędziu.'],
  ['Bary i puby', 'Szybki grafik, rozliczenia zmiany, rezerwacje stolików i lóż.'],
  ['Kawiarnie i food trucki', 'Prosty grafik, dyspozycyjność i RCP — start na planie darmowym.'],
]

const cenaLabel = (c) => (c === 'wycena' ? 'wycena' : `${c} zł`)

export default function Produkt() {
  return (
    <div className="relative min-h-dvh overflow-hidden bg-bg text-ink">
      <div aria-hidden className="pointer-events-none fixed -left-40 -top-40 h-[32rem] w-[32rem] rounded-full bg-page-glow opacity-[0.14] blur-3xl" />

      <div className="relative z-10 mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        {/* Nagłówek */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Logo className="h-8" variant="gradient" />
            <span className="font-display text-lg font-bold">Grafik Pracy</span>
          </div>
          <a href="/" className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted transition hover:text-ink">Zaloguj się</a>
        </header>

        {/* Hero */}
        <section className="py-16 text-center sm:py-24">
          <span className="inline-block rounded-full border border-line bg-surface-2/60 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-muted">
            System zarządzania lokalem gastronomicznym
          </span>
          <h1 className="mx-auto mt-5 max-w-3xl font-display text-4xl font-bold leading-tight sm:text-5xl">
            Zastąp Excel, papier i 3 osobne narzędzia <span className="bg-accent-gradient bg-clip-text text-transparent">jednym systemem</span>.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg">
            Grafik, ewidencja czasu, rozliczenia kasowe, rezerwacje i wesela — w jednym miejscu.
            Dla restauracji, domów weselnych i kawiarni. Web (PWA) i desktop.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <a href="#cennik" className="rounded-xl bg-accent-gradient px-6 py-3 text-sm font-bold text-bg shadow-cta transition hover:brightness-105">Zobacz cennik</a>
            <a href="mailto:kontakt@grafikpracy.pl?subject=Demo%20Grafik%20Pracy" className="rounded-xl border border-line px-6 py-3 text-sm font-semibold text-ink transition hover:bg-white/[0.05]">Umów demo</a>
          </div>
        </section>

        {/* Funkcje */}
        <section className="py-8">
          <h2 className="text-center font-display text-2xl font-bold sm:text-3xl">Cały obieg operacyjny lokalu</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(([ico, tytul, opis]) => (
              <div key={tytul} className="card p-6">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent-gradient text-bg">
                  <Icon name={ico} className="h-5 w-5" />
                </div>
                <h3 className="mt-4 font-display text-base font-bold">{tytul}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{opis}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Cennik */}
        <section id="cennik" className="scroll-mt-6 py-16">
          <h2 className="text-center font-display text-2xl font-bold sm:text-3xl">Prosty cennik — płacisz za lokal, nie za osobę</h2>
          <p className="mt-2 text-center text-sm text-muted">Ceny netto / miesiąc przy umowie rocznej. Dodatek integracji POS: +149 zł/mc.</p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {CENNIK.map((p) => (
              <div key={p.nazwa} className={`card flex flex-col p-5 ${p.flagowy ? 'ring-2 ring-mint' : ''}`}>
                {p.flagowy && <span className="mb-2 inline-block w-fit rounded-full bg-accent-gradient px-2.5 py-0.5 text-[11px] font-bold text-bg">Najpopularniejszy</span>}
                <h3 className="font-display text-lg font-bold">{p.nazwa}</h3>
                <div className="mt-1 flex items-baseline gap-1">
                  <span className="font-display text-3xl font-bold">{cenaLabel(p.cena)}</span>
                </div>
                <p className="mt-1 text-xs text-muted">{p.opis}</p>
                <ul className="mt-4 flex-1 space-y-2">
                  {p.cechy.map((c) => (
                    <li key={c} className="flex items-start gap-2 text-sm text-ink">
                      <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-mint" /> <span>{c}</span>
                    </li>
                  ))}
                </ul>
                <a href={p.cena === 'wycena' ? 'mailto:kontakt@grafikpracy.pl?subject=Enterprise' : 'mailto:kontakt@grafikpracy.pl?subject=Plan%20' + p.nazwa}
                  className={`mt-5 rounded-xl px-4 py-2.5 text-center text-sm font-bold transition ${p.flagowy ? 'bg-accent-gradient text-bg shadow-cta hover:brightness-105' : 'border border-line text-ink hover:bg-white/[0.05]'}`}>
                  {p.cena === '0' ? 'Zacznij za darmo' : p.cena === 'wycena' ? 'Zapytaj o wycenę' : 'Wybieram'}
                </a>
              </div>
            ))}
          </div>
        </section>

        {/* Dla kogo */}
        <section className="py-8">
          <h2 className="text-center font-display text-2xl font-bold sm:text-3xl">Dla kogo</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {SEGMENTY.map(([tytul, opis]) => (
              <div key={tytul} className="rounded-2xl border border-line bg-surface-2/50 p-5">
                <h3 className="font-display text-base font-bold">{tytul}</h3>
                <p className="mt-1.5 text-sm text-muted">{opis}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA końcowe */}
        <section className="my-12 rounded-3xl border border-line bg-surface-2/40 p-10 text-center">
          <h2 className="font-display text-2xl font-bold sm:text-3xl">Gotowy uporządkować lokal?</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted">Umów bezpłatne demo — pokażemy, jak przenieść grafik, rozliczenia i rezerwacje w jedno miejsce.</p>
          <a href="mailto:kontakt@grafikpracy.pl?subject=Demo%20Grafik%20Pracy" className="mt-6 inline-block rounded-xl bg-accent-gradient px-7 py-3 text-sm font-bold text-bg shadow-cta transition hover:brightness-105">Umów demo</a>
        </section>

        <footer className="border-t border-line py-8 text-center text-xs text-muted/70">
          © Grafik Pracy — oprogramowanie własnościowe. Wszelkie prawa zastrzeżone.
        </footer>
      </div>
    </div>
  )
}
