import { Icon } from '../../lib/icons'

// Sekcja „Cross-platform" — Lokalo Noir (DESIGN.md §8). Kompozycja trzech urządzeń
// zbudowanych czystym CSS (ramki glass): tablet · laptop · telefon, w środku abstrakcyjne
// szkice UI z div-ów (paski, kafle, jedna złota linia na urządzenie). Dekoracja: aria-hidden.

const PLATFORMY = ['iOS', 'Android', 'Windows', 'macOS', 'Web (PWA)', 'Tablet']

const CHECKI = [
  'Offline-friendly PWA',
  'Powiadomienia push',
  'Jeden system — zero ręcznych synchronizacji',
]

// Szkicowe „paski" i „kafle" wnętrza ekranów — bez tekstu, tylko rytm powierzchni.
function Pasek({ w = 'w-2/3' }) {
  return <div className={`h-1.5 rounded-full bg-white/[0.06] ${w}`} />
}

function Kafel({ h = 'h-8' }) {
  return <div className={`${h} rounded-md bg-white/[0.06]`} />
}

function ZlotaLinia({ w = 'w-12' }) {
  return <div className={`h-0.5 rounded-full bg-zloto/70 ${w}`} />
}

export default function SekcjaPlatformy() {
  return (
    <section id="platformy" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2
          data-head=""
          className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl"
          style={{ textWrap: 'balance' }}
        >
          Działa <span className="text-zloto">wszędzie</span>, gdzie Twój zespół.
        </h2>
        <p data-rv="" style={{ '--i': 1 }} className="mt-4 max-w-2xl text-muted">
          Personel ma aplikację zawsze pod ręką — instaluje się prosto z przeglądarki,{' '}
          <em className="font-editorial italic font-medium text-zloto-2">
            bez sklepów i bez działu IT
          </em>
          . Desktop dla biura, tablet na sali, telefon w kieszeni kelnera.
        </p>

        {/* Kompozycja urządzeń: tablet (tło) · laptop (środek) · telefon (front) */}
        <div
          aria-hidden
          data-rv=""
          style={{ '--i': 2 }}
          className="rv-scale relative mt-14 flex items-end justify-center"
        >
          {/* Tablet ~4:3 */}
          <div className="relative z-0 -mr-8 mb-3 w-32 shrink-0 sm:-mr-10 sm:w-56">
            <div className="glass aspect-[4/3] rounded-2xl p-2 sm:p-3">
              <div className="flex h-full flex-col gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2.5">
                <div className="flex items-center justify-between">
                  <Pasek w="w-1/3" />
                  <ZlotaLinia w="w-8" />
                </div>
                <div className="grid flex-1 grid-cols-2 gap-1.5">
                  <Kafel h="h-auto" />
                  <Kafel h="h-auto" />
                  <Kafel h="h-auto" />
                  <Kafel h="h-auto" />
                </div>
              </div>
            </div>
          </div>

          {/* Laptop / desktop: ekran z belką i 3 kropkami + podstawa */}
          <div className="relative z-10 w-52 shrink-0 sm:w-[400px]">
            <div className="glass tilt overflow-hidden rounded-2xl">
              <div className="flex items-center gap-1.5 border-b border-white/[0.08] px-3 py-2.5">
                <span className="h-2 w-2 rounded-full bg-white/[0.09]" />
                <span className="h-2 w-2 rounded-full bg-white/[0.09]" />
                <span className="h-2 w-2 rounded-full bg-white/[0.09]" />
              </div>
              <div className="grid grid-cols-[auto_1fr] gap-3 p-3 sm:p-4">
                <div className="w-8 space-y-1.5 sm:w-12">
                  <Pasek w="w-full" />
                  <Pasek w="w-full" />
                  <Pasek w="w-2/3" />
                  <Pasek w="w-full" />
                </div>
                <div className="space-y-2">
                  <div className="grid grid-cols-3 gap-1.5">
                    <Kafel h="h-9 sm:h-12" />
                    <Kafel h="h-9 sm:h-12" />
                    <Kafel h="h-9 sm:h-12" />
                  </div>
                  <div className="flex items-end gap-1 pt-1">
                    {[5, 8, 6, 10, 12, 9, 7].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-t bg-white/[0.06]"
                        style={{ height: `${h * 3}px` }}
                      />
                    ))}
                  </div>
                  <ZlotaLinia w="w-full" />
                  <Pasek w="w-1/2" />
                </div>
              </div>
            </div>
            <div className="relative left-1/2 h-2 w-[112%] -translate-x-1/2 rounded-b-xl border border-white/[0.10] bg-white/[0.04]" />
          </div>

          {/* Telefon pion ~9:19 z paskiem-notchem */}
          <div className="relative z-20 -ml-7 w-16 shrink-0 sm:-ml-9 sm:w-24">
            <div className="glass flex aspect-[9/19] flex-col rounded-[1.5rem] p-1.5 sm:p-2">
              <div className="mx-auto mt-1 h-1 w-8 rounded-full bg-white/[0.09]" />
              <div className="mt-2 flex flex-1 flex-col gap-1.5 rounded-xl border border-white/[0.06] bg-white/[0.02] p-2">
                <Pasek w="w-2/3" />
                <Kafel h="h-7" />
                <Kafel h="h-7" />
                <ZlotaLinia w="w-8" />
                <Pasek w="w-full" />
                <Pasek w="w-3/4" />
                <div className="mt-auto h-5 rounded-md bg-zloto/10" />
              </div>
            </div>
          </div>
        </div>

        {/* Ciche chipy platform */}
        <ul data-rv="" style={{ '--i': 3 }} className="mt-12 flex flex-wrap justify-center gap-2">
          {PLATFORMY.map((p) => (
            <li
              key={p}
              className="rounded-full border border-white/[0.10] bg-white/[0.02] px-3.5 py-1.5 text-xs font-medium text-muted"
            >
              {p}
            </li>
          ))}
        </ul>

        {/* Trzy konkrety */}
        <div className="mt-8 flex flex-col items-center justify-center gap-3 border-t border-white/[0.08] pt-8 sm:flex-row sm:gap-10">
          {CHECKI.map((c, i) => (
            <div
              key={c}
              data-rv=""
              style={{ '--i': 4 + i }}
              className="flex items-center gap-2.5 text-sm text-muted"
            >
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-mint/15">
                <Icon name="check" className="h-3.5 w-3.5 text-mint" />
              </span>
              {c}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
