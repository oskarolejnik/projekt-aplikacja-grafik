import { useState } from 'react'
import { Icon } from '../../lib/icons'
import { GrafikVignette, PulpitVignette, RezerwacjaVignette, WyplataVignette } from './Vignettes'

// Pokazy produktu na żywo: przełączane winiety realnego UI zamiast trzech osobnych
// sekcji showcase. Jeden ekran, cztery historie — użytkownik sam wybiera, co go boli.

const POKAZY = [
  {
    k: 'grafik', ikona: 'calendar', naz: 'Grafik i obsada',
    tytul: 'Grafik układa się z dyspozycyjności — nie w niedzielę w nocy',
    opis: 'Zespół zgłasza dyspozycyjność z telefonu, algorytm proponuje obsadę z kwalifikacji i urlopów, Ty zatwierdzasz i publikujesz jednym kliknięciem.',
    punkty: ['Auto-grafik z kwalifikacji i urlopów', 'Strażnik prawa pracy: odpoczynek i limity dni', 'Giełda wymiany zmian z akceptacją managera', 'Prognoza obsady z historii ruchu'],
    W: GrafikVignette,
  },
  {
    k: 'pulpit', ikona: 'clipboard', naz: 'Pulpit właściciela',
    tytul: 'Wiesz, co się dzieje — bez zaglądania w pięć miejsc',
    opis: 'Przychód, ruch, koszt pracy i saldo kasy w jednym widoku. Anomalie w rozliczeniach podświetlają się same, zanim urosną do problemu.',
    punkty: ['Przychód, rozchód i saldo kasy narastająco', 'Koszt pracy z RCP × stawki na żywo', 'Alerty różnic w rozliczeniu dnia', 'Prognoza ruchu na 7 dni'],
    W: PulpitVignette,
  },
  {
    k: 'rezerwacje', ikona: 'pin', naz: 'Rezerwacje',
    tytul: 'Własny kanał rezerwacji — bez prowizji portali',
    opis: 'Widget na Twojej stronie: gość rezerwuje w kilka sekund i dostaje potwierdzenie SMS + e-mail. Ty masz plan sali i historię gościa w panelu.',
    punkty: ['Rezerwacje online 0% prowizji', 'Interaktywny plan sali + lista oczekujących', 'CRM gościa ze scoringiem no-show'],
    W: RezerwacjaVignette,
  },
  {
    k: 'wyplaty', ikona: 'clock', naz: 'Wypłaty i portfel',
    tytul: 'Godziny z RCP → wypłaty co do minuty',
    opis: 'Odbicia czasu pracy spinają się z grafikiem i stawkami. Każdy widzi swoje godziny i kwotę na bieżąco — mniej sporów, zero przepisywania.',
    punkty: ['Godziny per stanowisko i dzień', 'Portfel pracownika: zarobki na żywo + zaliczki', 'Eksport wypłat do Excela dla księgowej'],
    W: WyplataVignette,
  },
]

export default function SekcjaPokazy() {
  const [aktywny, setAktywny] = useState('grafik')
  const pokaz = POKAZY.find((p) => p.k === aktywny)

  return (
    <section id="mozliwosci" className="relative scroll-mt-20 py-20 sm:py-28">
      <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
        <h2 data-rv="" className="font-brand text-3xl font-semibold tracking-tight text-ink sm:text-5xl" style={{ textWrap: 'balance' }}>
          Zobacz system <span className="text-zloto">przy pracy</span>.
        </h2>
        <p data-rv="" style={{ '--i': 1 }} className="mt-4 max-w-2xl text-muted">
          To nie makiety — tak wyglądają prawdziwe ekrany Lokalo. Wybierz obszar, który dziś zabiera Ci najwięcej czasu.
        </p>

        {/* Przełącznik obszarów — szklana listwa pigułek */}
        <div data-rv="" style={{ '--i': 2 }} className="mt-8 flex flex-wrap gap-2">
          {POKAZY.map((p) => (
            <button
              key={p.k}
              onClick={() => setAktywny(p.k)}
              aria-pressed={aktywny === p.k}
              className={`inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold transition duration-200 ${
                aktywny === p.k
                  ? 'border-white/[0.16] bg-white/[0.08] text-ink'
                  : 'border-white/[0.08] bg-white/[0.02] text-muted hover:border-white/[0.14] hover:text-ink'
              }`}
            >
              <Icon name={p.ikona} className={`h-4 w-4 ${aktywny === p.k ? 'text-zloto' : ''}`} />
              {p.naz}
            </button>
          ))}
        </div>

        {/* Scena pokazu: tekst + winieta; key wymusza wejście przy zmianie zakładki */}
        <div key={pokaz.k} className="mt-10 grid items-center gap-8 lg:grid-cols-2 lg:gap-14">
          <div className="animate-fade-up">
            <h3 className="font-brand text-2xl font-semibold text-ink sm:text-3xl" style={{ textWrap: 'balance' }}>{pokaz.tytul}</h3>
            <p className="mt-3 max-w-md leading-relaxed text-muted">{pokaz.opis}</p>
            <ul className="mt-5 space-y-2.5">
              {pokaz.punkty.map((p) => (
                <li key={p} className="flex items-start gap-2.5 text-sm text-ink">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-zloto" /> <span>{p}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="animate-fade-up mx-auto w-full max-w-md" style={{ animationDelay: '60ms' }}>
            <pokaz.W />
          </div>
        </div>
      </div>
    </section>
  )
}
