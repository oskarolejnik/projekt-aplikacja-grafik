// Sekcja landingu „Zaufanie" (rejestr Lokalo Noir): uczciwy trust — wyłącznie
// sprawdzalne liczby produktu i historia założyciela-operatora. Zero zmyślonych
// klientów, cytatów i logotypów.
import { Icon } from '../../lib/icons'

const LANCUCH = ['grafik', 'wypłaty', 'kasa', 'rezerwacje', 'imprezy']

const FAKTY = [
  {
    token: '0%',
    mint: true,
    tytul: 'prowizji od rezerwacji online.',
    opis: 'Portale rezerwacyjne potrafią brać 2–3 zł od każdego gościa. Rezerwacja z Twojego widgetu nie kosztuje nic.',
  },
  {
    token: 'RODO-first',
    tytul: 'szyfrowanie danych wrażliwych i dziennik audytu.',
    opis: 'Każde zajrzenie do płac zostawia ślad — wiesz kto, kiedy i do czyich danych sięgał.',
  },
  {
    token: 'PWA + desktop',
    tytul: 'telefon, tablet i komputer — jedna aplikacja.',
    opis: 'Twoje dane działają w Twojej instancji, nie na wspólnym serwerze z setką innych lokali.',
  },
]

const SCENARIUSZ = [
  { zadanie: 'Grafik na cały tydzień', przed: '3 h', po: '20 min' },
  { zadanie: 'Rozliczenie wieczoru', przed: '40 min', po: '5 min' },
  { zadanie: 'Odpowiedź na zapytanie o wesele', przed: '2 dni', po: '2 min' },
]

export default function SekcjaZaufanie() {
  return (
    <section id="zaufanie" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2
          data-head=""
          className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl"
          style={{ textWrap: 'balance' }}
        >
          Zbudowane na <span className="text-zloto">sali</span>, nie w sali konferencyjnej.
        </h2>
        <p data-rv="" style={{ '--i': 1 }} className="mt-4 max-w-2xl text-muted">
          Żadnych wynajętych twarzy ani wymyślonych opinii. Poniżej wyłącznie to, co da się
          sprawdzić: liczby produktu i historia człowieka, który go napisał.
        </p>

        {/* Dwie duże, nierówne karty faktów */}
        <div className="mt-12 grid gap-4 lg:mt-16 lg:grid-cols-5">
          <div data-rv="" className="rv-scale glass tilt rounded-3xl p-7 sm:p-9 lg:col-span-3">
            <p data-count="25" data-suffix="+" className="font-brand text-6xl font-semibold tabular-nums tracking-tight text-ink sm:text-7xl">
              25+
            </p>
            <p className="mt-2 font-medium text-ink">modułów w jednym systemie</p>
            <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">
              Jeden login prowadzi lokal od grafiku po rozliczenie wypłat — bez przepisywania
              danych między aplikacjami.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-2">
              {LANCUCH.map((modul, i) => (
                <span key={modul} className="flex items-center gap-2">
                  {i > 0 && <span className="text-zloto">→</span>}
                  <span className="rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1 text-xs text-muted">
                    {modul}
                  </span>
                </span>
              ))}
            </div>
          </div>

          <div
            data-rv=""
            style={{ '--i': 1 }}
            className="rv-scale glass flex flex-col justify-between rounded-3xl p-7 sm:p-9 lg:col-span-2"
          >
            <div className="flex items-start justify-between gap-4">
              <p data-count="500" data-suffix="+" className="font-brand text-6xl font-semibold tabular-nums tracking-tight text-ink sm:text-7xl">
                500+
              </p>
              <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-muted">
                <Icon name="clipboard" className="h-5 w-5" />
              </span>
            </div>
            <div className="mt-4">
              <p className="font-medium text-ink">
                testów automatycznych pilnuje każdej wypłaty i każdego rozliczenia
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Uruchamiane przy każdej zmianie w kodzie — zanim cokolwiek trafi do Twojego lokalu.
              </p>
            </div>
          </div>
        </div>

        {/* Trzy fakty jako wiersze — nie kolejna siatka kart */}
        <div data-rv="" style={{ '--i': 2 }} className="glass mt-4 rounded-3xl px-6 sm:px-9">
          {FAKTY.map((f, i) => (
            <div
              key={f.token}
              className={`flex flex-col gap-1.5 py-6 sm:flex-row sm:items-baseline sm:gap-8 ${
                i > 0 ? 'border-t border-white/[0.08]' : ''
              }`}
            >
              <p
                className={`shrink-0 font-brand text-2xl font-semibold tabular-nums tracking-tight sm:w-56 sm:text-3xl ${
                  f.mint ? 'text-mint' : 'text-ink'
                }`}
              >
                {f.token}
              </p>
              <div>
                <p className="font-medium text-ink">{f.tytul}</p>
                <p className="mt-1 text-sm leading-relaxed text-muted">{f.opis}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Historia założyciela + wyraźnie oznaczony scenariusz poglądowy */}
        <div className="mt-16 grid items-center gap-10 lg:grid-cols-2 lg:gap-14">
          <figure data-rv="" className="rv-l">
            <blockquote
              className="text-2xl leading-snug sm:text-[2rem] sm:leading-snug"
              style={{ textWrap: 'balance' }}
            >
              <em className="font-editorial italic font-medium text-zloto-2">
                „Zbudował to manager, który sam zamykał lokal w piątkowe noce — nie zespół, który
                gastro zna z prezentacji."
              </em>
            </blockquote>
            <figcaption className="mt-5 text-sm text-muted">
              Historia założyciela — system powstał na zmianach, które sam prowadził.
            </figcaption>
          </figure>

          <div data-rv="" style={{ '--i': 1 }} className="rv-r glass tilt rounded-3xl p-7 sm:p-8">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
              <Icon name="info" className="h-3.5 w-3.5" />
              scenariusz poglądowy
            </p>
            <h3 className="mt-2 font-brand text-xl font-semibold tracking-tight text-ink">
              Przykładowy tydzień managera
            </h3>
            <div className="mt-4">
              {SCENARIUSZ.map((s, i) => (
                <div
                  key={s.zadanie}
                  className={`flex items-baseline justify-between gap-4 py-4 ${
                    i > 0 ? 'border-t border-white/[0.08]' : ''
                  }`}
                >
                  <p className="text-sm text-ink">{s.zadanie}</p>
                  <p className="flex shrink-0 items-baseline gap-2 tabular-nums">
                    <span className="text-sm text-muted">{s.przed}</span>
                    <span className="text-muted">→</span>
                    <span className="font-brand text-2xl font-semibold text-ink sm:text-3xl">
                      {s.po}
                    </span>
                  </p>
                </div>
              ))}
            </div>
            <p className="border-t border-white/[0.08] pt-4 text-xs leading-relaxed text-muted">
              Szacunki na podstawie operacji lokalu, w którym system powstał — nie obietnica
              handlowa.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
