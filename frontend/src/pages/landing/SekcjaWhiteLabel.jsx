// Sekcja landingu „White-label" (rejestr Lokalo Noir): interaktywny podgląd,
// jak aplikacja wygląda pod marką konkretnego lokalu. Zero zależności poza React.
import { useState } from 'react'
import { Icon } from '../../lib/icons'

const MARKI = [
  {
    id: 'nonna',
    nazwa: 'Trattoria Nonna',
    kolor: '#C96A6A',
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
    id: 'neon',
    nazwa: 'Bar Mleczny Neon',
    kolor: '#9DC4B1',
    zmiana: 'wydawka + sala',
    grafik: [
      { kto: 'Staszek', szer: '84%' },
      { kto: 'Ula', szer: '58%' },
      { kto: 'Kamil', szer: '70%' },
    ],
    kafle: [
      { etykieta: 'Obiady dziś', wartosc: '214', podpis: 'szczyt 12:30–14:00' },
      { etykieta: 'Napiwki — wczoraj', wartosc: '96 zł', podpis: 'podział po godzinach' },
    ],
    moduly: ['Grafik', 'Kasa', 'Sprzątanie'],
  },
  {
    id: 'aurum',
    nazwa: 'Hotel Aurum',
    kolor: '#C9A96A',
    zmiana: 'bankiet — sala złota',
    grafik: [
      { kto: 'Klara', szer: '90%' },
      { kto: 'Tomasz', szer: '66%' },
      { kto: 'Iga', szer: '74%' },
    ],
    kafle: [
      { etykieta: 'Imprezy w tym tygodniu', wartosc: '3', podpis: 'wesele, chrzciny, konferencja' },
      { etykieta: 'Napiwki — wczoraj', wartosc: '1 240 zł', podpis: 'bankiet na 120 osób' },
    ],
    moduly: ['Grafik', 'Imprezy', 'Rezerwacje', 'CRM gości'],
  },
]

const PERSONALIZACJE = [
  { tytul: 'Logo i nazwa', opis: 'Twój znak w topbarze, w aplikacji na telefonie personelu i w PWA na ekranie głównym.' },
  { tytul: 'Kolor przewodni', opis: 'jeden wybór w panelu — akcent zmienia się w całej aplikacji, od przycisków po wykresy.' },
  { tytul: 'Włączone moduły', opis: 'personel widzi tylko to, czego naprawdę używacie. Bez martwych zakładek.' },
  { tytul: 'Ekran logowania', opis: 'powitanie w klimacie Twojego lokalu — nie naszej firmy.' },
  { tytul: 'Własna domena', opis: 'aplikacja pod Twoim adresem (plan Enterprise).' },
]

export default function SekcjaWhiteLabel() {
  const [aktywnaId, setAktywnaId] = useState(MARKI[0].id)
  const marka = MARKI.find((m) => m.id === aktywnaId) || MARKI[0]

  return (
    <section id="white-label" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2
          data-rv=""
          className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl"
          style={{ textWrap: 'balance' }}
        >
          Twoja aplikacja. Twoja <span className="text-zloto">marka</span>.
        </h2>
        <p data-rv="" style={{ '--i': 1 }} className="mt-4 max-w-2xl text-muted">
          White-label masz w standardzie, nie w dopłacie. Nazwę, logo, kolor przewodni i zestaw
          modułów zmieniasz w panelu — bez dotykania kodu. Personel otwiera aplikację i widzi
          Twoją markę, nie naszą.
        </p>

        <div className="mt-12 grid items-start gap-10 lg:mt-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-14">
          {/* Lewa kolumna: co personalizujesz */}
          <div>
            <ul className="space-y-4">
              {PERSONALIZACJE.map((p, i) => (
                <li key={p.tytul} data-rv="" style={{ '--i': i }} className="rv-l flex items-start gap-3">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-mint/15">
                    <Icon name="check" className="h-3 w-3 text-mint" />
                  </span>
                  <p className="text-sm leading-relaxed sm:text-[15px]">
                    <span className="font-medium text-ink">{p.tytul}</span>{' '}
                    <span className="text-muted">— {p.opis}</span>
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
            <div data-rv="" className="rv-r flex flex-wrap gap-2" role="group" aria-label="Wybierz przykładową markę">
              {MARKI.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setAktywnaId(m.id)}
                  aria-pressed={m.id === aktywnaId}
                  className={`flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-colors duration-300 ${
                    m.id === aktywnaId
                      ? 'border-white/[0.16] bg-white/[0.06] text-ink'
                      : 'border-white/[0.08] bg-white/[0.02] text-muted hover:bg-white/[0.04] hover:text-ink'
                  }`}
                >
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: m.kolor }} />
                  {m.nazwa}
                </button>
              ))}
            </div>

            <div data-rv="" style={{ '--i': 1 }} className="rv-scale mt-4">
              <div className="glass tilt rounded-3xl p-3 sm:p-4">
                {/* Topbar aplikacji pod marką lokalu */}
                <div className="flex items-center justify-between rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <span
                      className="h-2.5 w-2.5 rounded-full transition-colors duration-500"
                      style={{ backgroundColor: marka.kolor }}
                    />
                    <span className="text-sm font-semibold text-ink">{marka.nazwa}</span>
                  </div>
                  <div className="flex items-center gap-3 text-muted">
                    <Icon name="bell" className="h-4 w-4" />
                    <Icon name="menu" className="h-4 w-4" />
                  </div>
                </div>

                {/* Kafle z akcentem w kolorze marki */}
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div className="col-span-2 rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-semibold text-ink">Grafik — {marka.zmiana}</p>
                      <span
                        className="rounded-full px-2 py-0.5 text-[11px] font-semibold transition-colors duration-500"
                        style={{ backgroundColor: `${marka.kolor}2E`, color: marka.kolor }}
                      >
                        obsada ok
                      </span>
                    </div>
                    <div className="mt-3 space-y-2.5">
                      {marka.grafik.map((z, i) => (
                        <div key={z.kto} className="flex items-center gap-3">
                          <span className="w-16 shrink-0 text-[11px] text-muted">{z.kto}</span>
                          <span className="h-1.5 flex-1 rounded-full bg-white/[0.04]">
                            <span
                              className="block h-full rounded-full transition-all duration-500"
                              style={{
                                width: z.szer,
                                backgroundColor: marka.kolor,
                                opacity: 0.85 - i * 0.22,
                              }}
                            />
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {marka.kafle.map((k) => (
                    <div key={k.etykieta} className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                      <p className="text-[11px] text-muted">{k.etykieta}</p>
                      <p
                        className="mt-1 font-brand text-2xl font-semibold tabular-nums transition-colors duration-500"
                        style={{ color: marka.kolor }}
                      >
                        {k.wartosc}
                      </p>
                      <p className="mt-0.5 text-[11px] text-muted">{k.podpis}</p>
                    </div>
                  ))}
                </div>

                {/* Zestaw modułów włączonych dla tej marki */}
                <div className="mt-3 flex flex-wrap items-center gap-2 px-1 pb-1">
                  <span className="text-[11px] text-muted">Włączone moduły:</span>
                  {marka.moduly.map((mod) => (
                    <span
                      key={mod}
                      className="flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.02] px-2.5 py-1 text-[11px] text-muted"
                    >
                      <span
                        className="h-1.5 w-1.5 rounded-full transition-colors duration-500"
                        style={{ backgroundColor: marka.kolor }}
                      />
                      {mod}
                    </span>
                  ))}
                </div>
              </div>
              <p className="mt-3 text-center text-xs text-muted">
                Podgląd poglądowy — przełącz markę, żeby zobaczyć zmianę bez ani jednej linii kodu.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
