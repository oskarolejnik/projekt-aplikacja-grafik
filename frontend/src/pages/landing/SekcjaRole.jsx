import { Icon } from '../../lib/icons'
import { PulpitVignette, GrafikVignette } from './Vignettes'

// Sekcja „System ról" — Lokalo Noir (DESIGN.md §8). Kompozycja asymetryczna:
// 2 duże karty-pokazy (właściciel, manager) z podglądem realnego ekranu roli
// + 4 kompaktowe role zespołu. Złota nitka = pojedyncze słowo + ikony dużych kart.

const ROLE_DUZE = [
  {
    ikona: 'office',
    nazwa: 'Właściciel',
    opis: 'Liczby lokalu bez dzwonienia na zmianę — pełna kontrola z dowolnego miejsca.',
    punkty: [
      'Pulpit KPI i przychody dnia na żywo',
      'Koszt pracy liczony w tle każdej zmiany',
      'Antyfraud POS — flagi stornowań i rabatów',
    ],
    Podglad: PulpitVignette,
  },
  {
    ikona: 'calendar',
    nazwa: 'Manager',
    opis: 'Cała operacja tygodnia w jednym miejscu — od grafiku po terminy badań.',
    punkty: [
      'Układa i publikuje grafik zespołu',
      'Akceptuje urlopy i zaliczki jednym ruchem',
      'Pilnuje zgodności — sanepid, badania, terminy',
    ],
    Podglad: GrafikVignette,
  },
]

const ROLE_MALE = [
  {
    ikona: 'clock',
    nazwa: 'Kelner / obsługa',
    punkty: [
      '„Twoje godziny" i portfel — zarobki na żywo',
      'Giełda wymiany zmian i napiwki',
      'Dyspozycyjność zgłaszana z telefonu',
    ],
  },
  {
    ikona: 'clipboard',
    nazwa: 'Kuchnia',
    punkty: [
      'Własny grafik kuchni',
      'Godziny i stawki niezależne od sali',
      'Widok szefa kuchni',
    ],
  },
  {
    ikona: 'pin',
    nazwa: 'Bar',
    punkty: [
      'Własne rewiry na sali',
      'Rozliczenie zmiany krok po kroku',
      'Zamknięcie kasy swojego rewiru',
    ],
  },
  {
    ikona: 'sparkles',
    nazwa: 'Technika / sprzątanie',
    punkty: [
      'Grafik sprzątania sal',
      'Zamówienia środków czystości',
      'Własne godziny i rozliczenia',
    ],
  },
]

function MikroEtykieta() {
  return (
    <div className="mt-auto flex items-center gap-2 border-t border-white/[0.08] pt-3">
      <Icon name="key" className="h-3 w-3 text-muted" />
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
        własny widok i uprawnienia
      </span>
    </div>
  )
}

export default function SekcjaRole() {
  return (
    <section id="role" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2
          data-rv=""
          className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl"
          style={{ textWrap: 'balance' }}
        >
          Każda <span className="text-zloto">rola</span> widzi swój lokal.
        </h2>
        <p data-rv="" style={{ '--i': 1 }} className="mt-4 max-w-2xl text-muted">
          System ról i uprawnień: każdy członek zespołu dostaje własny, dopasowany widok — bez
          zbędnych zakładek i cudzych danych. Wrażliwe informacje zostają tam, gdzie ich miejsce:{' '}
          <em className="font-editorial italic font-medium text-zloto-2">
            płace widzi tylko uprawniony
          </em>
          .
        </p>

        {/* Dwie duże karty-pokazy: role zarządcze */}
        <div className="mt-12 grid gap-4 lg:grid-cols-2">
          {ROLE_DUZE.map((rola, i) => (
            <article
              key={rola.nazwa}
              data-rv=""
              style={{ '--i': 2 + i }}
              className="glass tilt rv-scale relative flex flex-col rounded-3xl p-6 sm:p-8"
            >
              <div className="flex items-center gap-4">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full border border-white/[0.10] bg-white/[0.06]">
                  <Icon name={rola.ikona} className="h-5 w-5 text-zloto" />
                </span>
                <h3 className="font-brand text-2xl font-semibold text-ink">{rola.nazwa}</h3>
              </div>
              <p className="mt-4 text-sm text-muted">{rola.opis}</p>
              <ul className="mt-5 space-y-2.5">
                {rola.punkty.map((p) => (
                  <li key={p} className="flex items-start gap-2.5 text-sm text-muted">
                    <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-mint/15">
                      <Icon name="check" className="h-3 w-3 text-mint" />
                    </span>
                    {p}
                  </li>
                ))}
              </ul>
              {/* Podgląd realnego ekranu tej roli — „pokaż, nie opowiadaj" */}
              <div className="mt-6">
                <rola.Podglad />
              </div>
              <div className="pt-6" />
              <MikroEtykieta />
            </article>
          ))}
        </div>

        {/* Cztery kompaktowe role zespołu */}
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ROLE_MALE.map((rola, i) => (
            <article
              key={rola.nazwa}
              data-rv=""
              style={{ '--i': 4 + i }}
              className="glass rv-scale flex flex-col rounded-2xl p-5"
            >
              <span className="grid h-10 w-10 place-items-center rounded-full border border-white/[0.10] bg-white/[0.06]">
                <Icon name={rola.ikona} className="h-4 w-4 text-muted" />
              </span>
              <h3 className="mt-3 font-brand text-lg font-semibold text-ink">{rola.nazwa}</h3>
              <ul className="mt-2.5 space-y-1.5">
                {rola.punkty.map((p) => (
                  <li key={p} className="flex items-start gap-2 text-[13px] leading-snug text-muted">
                    <Icon name="check" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mint" />
                    {p}
                  </li>
                ))}
              </ul>
              <div className="pt-4" />
              <MikroEtykieta />
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
