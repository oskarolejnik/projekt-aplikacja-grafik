// Sekcja „Za darmo" (rejestr Lokalo Noir) — umieszczona WYSOKO (zaraz po PainRelief),
// bo bezpłatny start to najsilniejszy argument wejścia. Zamiast krzykliwego badge'a
// tłumaczy MECHANIKĘ próby jako oś czasu 0 → 14 → ∞ (realna sekwencja, nie ozdobnik):
// dziś pełny Premium bez karty, po 14 dniach wybór planu, a jak nie wybierzesz —
// zostajesz na Darmowym na zawsze. Oś łączy włoskowata linia (pozioma na desktopie,
// pionowa na telefonie); numery-dni maskują linię solidnym tłem = spięte węzły.

const KROKI = [
  {
    dzien: '0',
    ton: 'text-zloto',
    kropka: 'border-zloto/40',
    ety: 'Dziś',
    txt: 'Wybierasz plan i podajesz kartę. Masz 14 dni pełnego dostępu — dziś nie pobieramy ani grosza.',
  },
  {
    dzien: '14',
    ton: 'text-ink',
    kropka: 'border-white/20',
    ety: 'Po 14 dniach',
    txt: 'Plan włącza się automatycznie i karta zostaje obciążona. Rezygnujesz? Anuluj wcześniej.',
  },
  {
    dzien: '∞',
    ton: 'text-mint',
    kropka: 'border-mint/40',
    ety: 'Bez zobowiązań',
    txt: 'Wolisz bez karty? Plan Darmowy działa zawsze — 0 zł, rdzeń w komplecie.',
  },
]

export default function SekcjaTrial() {
  return (
    <section id="za-darmo" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <div className="max-w-2xl">
          <h2
            data-head=""
            className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl"
            style={{ textWrap: 'balance' }}
          >
            Pierwsze <span className="text-zloto">14 dni</span> bierzesz na próbę.
          </h2>
          <p data-rv="" style={{ '--i': 1 }} className="mt-4 text-muted sm:text-lg">
            14 dni <em className="font-editorial italic font-medium text-zloto-2">pełnego dostępu</em>,
            zero opłat z góry. Kartę obciążamy dopiero po dwóch tygodniach — anuluj wcześniej i nie
            pobierzemy nic.
          </p>
        </div>

        {/* Oś czasu próby: 0 → 14 → ∞. Linia łącząca pod numerami (poziom desktop / pion mobile). */}
        <ol className="relative mt-12 grid gap-9 sm:mt-16 sm:grid-cols-3 sm:gap-8">
          {/* linia pozioma (desktop) — na wysokości środka kafla numeru (h-14 → top-7) */}
          <span aria-hidden className="absolute left-8 right-8 top-7 hidden h-px bg-gradient-to-r from-zloto/25 via-white/10 to-mint/25 sm:block" />
          {/* linia pionowa (mobile) — na osi środka kafla numeru (w-14 → left-7) */}
          <span aria-hidden className="absolute bottom-6 left-7 top-6 w-px bg-gradient-to-b from-zloto/25 via-white/10 to-mint/25 sm:hidden" />

          {KROKI.map((k, i) => (
            <li
              key={k.dzien}
              data-rv=""
              style={{ '--i': i }}
              className="relative flex items-start gap-5 sm:flex-col sm:gap-5"
            >
              <span
                className={`relative z-10 flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border bg-noc font-brand text-2xl font-bold tabular-nums ${k.ton} ${k.kropka}`}
              >
                {k.dzien}
              </span>
              <div className="pt-1.5 sm:pt-0">
                <div className={`text-xs font-semibold uppercase tracking-[0.14em] ${k.ton} opacity-90`}>
                  {k.ety}
                </div>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{k.txt}</p>
              </div>
            </li>
          ))}
        </ol>

        <div data-rv="" style={{ '--i': 3 }} className="mt-12 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <a
            href="?start"
            className="rounded-xl bg-zloto px-6 py-3.5 text-sm font-semibold text-noc transition-colors hover:bg-zloto-2 active:scale-[0.98]"
          >
            Zacznij za darmo
          </a>
          <span className="text-xs text-muted">
            Konto zakładasz w minutę. Obciążamy dopiero po 14 dniach — anuluj, kiedy chcesz.
          </span>
        </div>
      </div>
    </section>
  )
}
