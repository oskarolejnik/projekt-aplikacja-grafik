import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { Spinner } from '../components/ui/Spinner'
import Onboarding from './Onboarding'

// ?start — brama „Zacznij za darmo" z landingu. Na świeżej instancji (0 użytkowników)
// od razu otwiera kreator lokalu; na działającej pokazuje uczciwy rozjazd zamiast
// wrzucania gościa w ekran logowania cudzego lokalu (feedback: „nie da się przejść
// do kreatora, a rejestracja tworzy konto pracownika").
const MAIL = 'mailto:kontakt@grafikpracy.pl'

export default function Start() {
  const [status, setStatus] = useState(null) // null = sprawdzam; { potrzebny, nazwa_lokalu }
  useEffect(() => {
    api('/onboarding/status')
      .then(setStatus)
      .catch(() => setStatus({ potrzebny: false, nazwa_lokalu: 'ten lokal' }))
  }, [])

  if (status === null) {
    return (
      <div className="grid min-h-dvh place-items-center bg-bg">
        <Spinner className="h-7 w-7 text-muted" />
      </div>
    )
  }

  // Świeża instancja → pełny kreator (konto właściciela + typ lokalu + moduły).
  if (status.potrzebny) return <Onboarding />

  const nazwa = status.nazwa_lokalu || 'ten lokal'
  const sciezki = [
    {
      ikona: 'office',
      tytul: 'Zakładam własny lokal',
      opis: `Każda restauracja dostaje własną, odizolowaną instancję — Twoje dane nie mieszkają na wspólnym serwerze. Napisz do nas, a postawimy Ci czysty lokal z kreatorem konfiguracji.`,
      cta: 'Napisz — stawiamy lokal',
      href: `${MAIL}?subject=${encodeURIComponent('Nowy lokal na Lokalo')}`,
      glowna: true,
    },
    {
      ikona: 'users',
      tytul: `Dołączam do zespołu ${nazwa}`,
      opis: 'Pracujesz tutaj? Załóż konto pracownika — zobaczysz swój grafik, godziny i portfel. Manager zatwierdzi Cię po pierwszym logowaniu.',
      cta: 'Załóż konto pracownika',
      href: '?login&tryb=rejestracja',
    },
    {
      ikona: 'key',
      tytul: 'Mam już konto',
      opis: `Wracasz do panelu lokalu ${nazwa}? Zaloguj się jak zwykle.`,
      cta: 'Zaloguj się',
      href: '?login',
    },
  ]

  return (
    <div className="relative min-h-dvh bg-bg text-ink">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-2xl flex-col justify-center px-4 py-10 sm:px-6">
        <div className="mb-8 flex items-center gap-2.5">
          <Logo className="h-8" variant="gradient" />
          <span className="font-display text-lg font-bold">Lokalo</span>
        </div>

        <h1 className="font-display text-2xl font-bold sm:text-3xl" style={{ textWrap: 'balance' }}>
          Od czego zaczynamy?
        </h1>
        <p className="mt-2 max-w-lg text-sm text-muted">
          Ta instalacja Lokalo prowadzi już lokal <span className="font-semibold text-ink">{nazwa}</span> —
          dlatego kreator nowego lokalu nie otworzy się tutaj. Wybierz swoją ścieżkę:
        </p>

        <div className="mt-7 space-y-4">
          {sciezki.map((s) => (
            <a
              key={s.tytul}
              href={s.href}
              className={`card flex items-start gap-4 rounded-2xl p-5 transition duration-200 hover:border-white/[0.16] active:scale-[0.99] ${
                s.glowna ? 'border-mint/30' : ''
              }`}
            >
              <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${s.glowna ? 'bg-mint/15 text-mint' : 'bg-white/[0.06] text-muted'}`}>
                <Icon name={s.ikona} className="h-5 w-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-display text-base font-bold text-ink">{s.tytul}</span>
                <span className="mt-1 block text-sm leading-relaxed text-muted">{s.opis}</span>
                <span className={`mt-3 inline-flex items-center gap-1.5 text-sm font-semibold ${s.glowna ? 'text-mint' : 'text-ink'}`}>
                  {s.cta} <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
                </span>
              </span>
            </a>
          ))}
        </div>

        <a href="?produkt" className="mt-8 text-center text-xs text-muted transition hover:text-ink">
          ← Wróć na stronę Lokalo
        </a>
      </div>
    </div>
  )
}
