// Sekcja landingu „White-label" (rejestr Lokalo Noir): interaktywny podgląd,
// jak aplikacja wygląda pod marką konkretnego lokalu. Przykłady zmieniają nie
// tylko kolor: nazwę, kształt znaku, zaokrąglenia (styl), zestaw modułów
// i CAŁY układ ekranu — bo każdy typ lokalu używa innych modułów na co dzień.
import { useEffect, useRef, useState } from 'react'
import { Icon } from '../../lib/icons'
import { gsap, reducedMotion } from './motionPro'

const PRZYKLADY = [
  {
    id: 'p1',
    przycisk: 'Przykład 1',
    krotka: 'Restauracja',
    lokal: 'Trattoria Nonna',
    podtytul: 'restauracja z ogródkiem',
    kolor: '#C96A6A',
    znak: 'rounded-full',            // kropka
    radius: 'rounded-xl',            // miękki styl
    uklad: 'grafik',
    zmiana: 'sala + ogródek',
    grafik: [
      { kto: 'Anna K.', szer: '78%' },
      { kto: 'Marco', szer: '62%' },
      { kto: 'Jagoda', szer: '88%' },
    ],
    kafle: [
      { etykieta: 'Rezerwacje dziś', wartosc: '18', podpis: 'w tym 2 stoliki rodzinne' },
      { etykieta: 'Napiwki — wczoraj', wartosc: '342 zł', podpis: 'rozliczone co do złotówki' },
    ],
    moduly: ['Grafik', 'Rezerwacje', 'Napiwki'],
  },
  {
    id: 'p2',
    przycisk: 'Przykład 2',
    krotka: 'Bar',
    lokal: 'Bar Neon',
    podtytul: 'bar szybkiej obsługi',
    kolor: '#9DC4B1',
    znak: 'rounded-[4px]',           // kwadrat
    radius: 'rounded-md',            // ostrzejszy styl
    uklad: 'wydawka',
    zmiana: 'wydawka + sala',
    zadania: [
      { co: 'Stolik 4 · 2× pierogi', stan: 'wydane', ok: true },
      { co: 'Na wynos #31 · schabowy', stan: 'w przygotowaniu', ok: false },
      { co: 'Stolik 2 · zupa dnia', stan: 'wydane', ok: true },
    ],
    kafleSzeroki: { etykieta: 'Obiady dziś', wartosc: '214', podpis: 'szczyt 12:30–14:00 · średni czas wydania 6 min' },
    moduly: ['Grafik', 'Kasa', 'Sprzątanie'],
  },
  {
    id: 'p3',
    przycisk: 'Przykład 3',
    krotka: 'Dom weselny',
    lokal: 'Hotel Aurum',
    podtytul: 'dom weselny przy hotelu',
    kolor: '#C9A96A',
    znak: 'rotate-45 rounded-[3px]', // romb
    radius: 'rounded-2xl',           // wystawny styl
    uklad: 'imprezy',
    zmiana: 'bankiet — sala złota',
    imprezy: [
      { co: 'Wesele · sala złota', kiedy: 'sob · 120 gości', chip: 'zadatek ✓' },
      { co: 'Konferencja · foyer', kiedy: 'pt · 80 osób', chip: 'oferta wysłana' },
    ],
    kafleSzeroki: { etykieta: 'Zadatki w kasie', wartosc: '12 400 zł', podpis: '3 imprezy w tym tygodniu' },
    moduly: ['Grafik', 'Imprezy', 'Rezerwacje', 'CRM gości'],
  },
]

const PERSONALIZACJE = [
  { tytul: 'Logo i nazwa', opis: 'Twój znak w topbarze, w aplikacji na telefonie personelu i w PWA na ekranie głównym.' },
  { tytul: 'Kolor przewodni', opis: 'jeden wybór w panelu — akcent zmienia się w całej aplikacji, od przycisków po wykresy.' },
  { tytul: 'Styl interfejsu', opis: 'kształt znaku i zaokrąglenia — od miękkiej trattorii po ostry bar szybkiej obsługi.' },
  { tytul: 'Włączone moduły', opis: 'personel widzi tylko to, czego naprawdę używacie. Bez martwych zakładek.' },
  { tytul: 'Ekran logowania i domena', opis: 'powitanie w klimacie Twojego lokalu; własny adres w planie Enterprise.' },
]

export default function SekcjaWhiteLabel() {
  const [aktywnyId, setAktywnyId] = useState(PRZYKLADY[0].id)
  const p = PRZYKLADY.find((m) => m.id === aktywnyId) || PRZYKLADY[0]
  const panelRef = useRef(null)
  const pierwszy = useRef(true)

  // Zmiana marki = panel PODGLĄDU obraca się w 3D (rotateY flip-in) — brand „przekręca się"
  // w nową tożsamość. Pierwszy render pomijamy (wejście robi reveal); reduced-motion → bez flipu.
  useEffect(() => {
    if (pierwszy.current) { pierwszy.current = false; return }
    if (reducedMotion() || !panelRef.current) return
    gsap.fromTo(panelRef.current,
      { rotateY: 26, opacity: 0.5, scale: 0.965 },
      { rotateY: 0, opacity: 1, scale: 1, duration: 0.8, ease: 'power3.out', overwrite: true })
  }, [aktywnyId])

  return (
    <section id="white-label" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2
          data-head=""
          className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl"
          style={{ textWrap: 'balance' }}
        >
          Twoja aplikacja. Twoja <span className="text-zloto">marka</span>.
        </h2>
        <p data-rv="" style={{ '--i': 1 }} className="mt-4 max-w-2xl text-muted">
          White-label masz w standardzie, nie w dopłacie. Nazwę, logo, kolor przewodni, styl i zestaw
          modułów zmieniasz w panelu — bez dotykania kodu. Personel otwiera aplikację i widzi
          Twoją markę, nie naszą.
        </p>

        <div className="mt-12 grid items-start gap-10 lg:mt-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14">
          {/* Lewa kolumna: co personalizujesz */}
          <div>
            <ul className="space-y-4">
              {PERSONALIZACJE.map((per, i) => (
                <li key={per.tytul} data-rv="" style={{ '--i': i }} className="rv-l flex items-start gap-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-mint/15">
                    <Icon name="check" className="h-3 w-3 text-mint" />
                  </span>
                  <p className="text-sm leading-relaxed sm:text-[15px]">
                    <span className="font-medium text-ink">{per.tytul}</span>{' '}
                    <span className="text-muted">— {per.opis}</span>
                  </p>
                </li>
              ))}
            </ul>
            <p data-rv="" style={{ '--i': 5 }} className="mt-9 text-lg sm:text-xl">
              <em className="font-editorial italic font-medium text-zloto-2">
                Twoja aplikacja. Twoja marka. 100% personalizacji.
              </em>
            </p>
          </div>

          {/* Prawa kolumna: interaktywny podgląd zmiany marki */}
          <div>
            {/* Segmentowy przełącznik marek — równe pola, wspólny tor (zamiast zawijających
                się „pigułek"). Etykiety = typ lokalu (sens > „Przykład 1"); na telefonie
                pełna szerokość 3 kolumny, na desktopie zwarty inline. */}
            <div
              data-rv=""
              className="rv-r relative grid grid-cols-3 gap-1.5 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-1.5 sm:inline-grid sm:auto-cols-max sm:grid-flow-col"
              role="group"
              aria-label="Wybierz przykładową konfigurację"
            >
              {PRZYKLADY.map((m) => {
                const on = m.id === aktywnyId
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setAktywnyId(m.id)}
                    aria-pressed={on}
                    className={`flex min-h-11 items-center justify-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-xs font-semibold transition-colors duration-200 sm:px-4 sm:text-[13px] ${
                      on
                        ? 'bg-white/[0.07] text-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]'
                        : 'text-muted hover:text-ink'
                    }`}
                  >
                    <span
                      className="h-2 w-2 shrink-0 rounded-full transition-transform duration-300"
                      style={{ backgroundColor: m.kolor, transform: on ? 'scale(1.3)' : 'scale(1)' }}
                    />
                    {m.krotka}
                  </button>
                )
              })}
            </div>

            <div data-rv="" style={{ '--i': 1, perspective: '1200px' }} className="rv-scale mt-4">
              <div ref={panelRef} className="glass rounded-3xl p-3 sm:p-4" style={{ transformStyle: 'preserve-3d' }}>
                {/* Topbar aplikacji pod marką lokalu: znak (kształt!) + nazwa */}
                <div className={`flex items-center justify-between border border-white/[0.08] bg-white/[0.03] px-4 py-3 ${p.radius}`}>
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`h-2.5 w-2.5 transition-colors duration-500 ${p.znak}`}
                      style={{ backgroundColor: p.kolor }}
                    />
                    <span className="text-sm font-semibold text-ink">{p.lokal}</span>
                    <span className="hidden text-[11px] text-muted sm:inline">· {p.podtytul}</span>
                  </div>
                  <div className="flex items-center gap-3 text-muted">
                    <Icon name="bell" className="h-4 w-4" />
                    <Icon name="menu" className="h-4 w-4" />
                  </div>
                </div>

                {/* Treść ekranu — INNY układ per przykład (moduły, których lokal używa) */}
                <div key={p.id} className="animate-fade-up mt-3">
                  {p.uklad === 'grafik' && (
                    <div className="grid grid-cols-2 gap-3">
                      <div className={`col-span-2 border border-white/[0.08] bg-white/[0.02] p-4 ${p.radius}`}>
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-semibold text-ink">Grafik — {p.zmiana}</p>
                          <span
                            className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                            style={{ backgroundColor: `${p.kolor}2E`, color: p.kolor }}
                          >
                            obsada ok
                          </span>
                        </div>
                        <div className="mt-3 space-y-2.5">
                          {p.grafik.map((z, i) => (
                            <div key={z.kto} className="flex items-center gap-3">
                              <span className="w-16 shrink-0 text-[11px] text-muted">{z.kto}</span>
                              <span className="h-1.5 flex-1 rounded-full bg-white/[0.04]">
                                <span
                                  className="block h-full rounded-full"
                                  style={{ width: z.szer, backgroundColor: p.kolor, opacity: 0.85 - i * 0.22 }}
                                />
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                      {p.kafle.map((k) => (
                        <div key={k.etykieta} className={`border border-white/[0.08] bg-white/[0.02] p-4 ${p.radius}`}>
                          <p className="text-[11px] text-muted">{k.etykieta}</p>
                          <p className="mt-1 font-brand text-2xl font-semibold tabular-nums" style={{ color: p.kolor }}>
                            {k.wartosc}
                          </p>
                          <p className="mt-0.5 text-[11px] text-muted">{k.podpis}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {p.uklad === 'wydawka' && (
                    <div className="space-y-3">
                      <div className={`border border-white/[0.08] bg-white/[0.02] p-4 ${p.radius}`}>
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-semibold text-ink">Wydawka — {p.zmiana}</p>
                          <span
                            className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                            style={{ backgroundColor: `${p.kolor}2E`, color: p.kolor }}
                          >
                            na bieżąco
                          </span>
                        </div>
                        <div className="mt-3 space-y-2">
                          {p.zadania.map((z) => (
                            <div key={z.co} className="flex items-center justify-between gap-3 text-[11px]">
                              <span className="flex min-w-0 items-center gap-2">
                                <span
                                  className="grid h-4 w-4 shrink-0 place-items-center rounded-full"
                                  style={{ backgroundColor: z.ok ? `${p.kolor}2E` : 'rgba(255,255,255,0.05)', color: p.kolor }}
                                >
                                  {z.ok && <Icon name="check" className="h-2.5 w-2.5" />}
                                </span>
                                <span className="truncate text-ink">{z.co}</span>
                              </span>
                              <span className="shrink-0 text-muted">{z.stan}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className={`border border-white/[0.08] bg-white/[0.02] p-4 ${p.radius}`}>
                        <p className="text-[11px] text-muted">{p.kafleSzeroki.etykieta}</p>
                        <p className="mt-1 font-brand text-2xl font-semibold tabular-nums" style={{ color: p.kolor }}>
                          {p.kafleSzeroki.wartosc}
                        </p>
                        <p className="mt-0.5 text-[11px] text-muted">{p.kafleSzeroki.podpis}</p>
                      </div>
                    </div>
                  )}

                  {p.uklad === 'imprezy' && (
                    <div className="space-y-3">
                      <div className={`border border-white/[0.08] bg-white/[0.02] p-4 ${p.radius}`}>
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-semibold text-ink">Imprezy — {p.zmiana}</p>
                          <span
                            className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                            style={{ backgroundColor: `${p.kolor}2E`, color: p.kolor }}
                          >
                            ten tydzień
                          </span>
                        </div>
                        <div className="mt-3 space-y-2">
                          {p.imprezy.map((im) => (
                            <div key={im.co} className="flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-[11px] font-semibold text-ink">{im.co}</p>
                                <p className="text-[10px] text-muted">{im.kiedy}</p>
                              </div>
                              <span
                                className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                                style={{ backgroundColor: `${p.kolor}2E`, color: p.kolor }}
                              >
                                {im.chip}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div className={`border border-white/[0.08] bg-white/[0.02] p-4 ${p.radius}`}>
                        <p className="text-[11px] text-muted">{p.kafleSzeroki.etykieta}</p>
                        <p className="mt-1 font-brand text-2xl font-semibold tabular-nums" style={{ color: p.kolor }}>
                          {p.kafleSzeroki.wartosc}
                        </p>
                        <p className="mt-0.5 text-[11px] text-muted">{p.kafleSzeroki.podpis}</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Zestaw modułów włączonych w tym przykładzie */}
                <div className="mt-3 flex flex-wrap items-center gap-2 px-1 pb-1">
                  <span className="text-[11px] text-muted">Włączone moduły:</span>
                  {p.moduly.map((mod) => (
                    <span
                      key={mod}
                      className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.02] px-2.5 py-1 text-[11px] text-muted"
                    >
                      <span className={`h-1.5 w-1.5 ${p.znak}`} style={{ backgroundColor: p.kolor }} />
                      {mod}
                    </span>
                  ))}
                </div>
              </div>
              <p className="mt-3 text-center text-xs text-muted">
                Podgląd poglądowy — przełącz przykład: zmienia się nazwa, kolor, styl, moduły i układ ekranu.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
