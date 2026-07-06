import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { Spinner } from '../components/ui/Spinner'
import Onboarding from './Onboarding'
import KreatorLokalu from './KreatorLokalu'

// Pakiet z cennika (?start&plan=pro) → wstępnie zaznaczony w kroku „plan" kreatora.
const PLAN = (() => {
  const p = (new URLSearchParams(window.location.search).get('plan') || '').toLowerCase()
  return ['darmowy', 'basic', 'pro', 'premium'].includes(p) ? p : null
})()
const PLAN_ETYKIETA = { darmowy: 'Darmowy', basic: 'Basic', pro: 'Pro', premium: 'Premium' }

// ?start — brama „Zacznij za darmo" z landingu. Świeża instancja (0 użytkowników) → pełny
// kreator instancji (fallback operatorski). Działająca instancja z włączoną samoobsługą →
// kreator lokalu Z PŁATNOŚCIĄ (KreatorLokalu): dane właściciela + plan → checkout → dopiero
// po opłaceniu backend stawia nową instancję z gotowym adminem i przenosi na ?login.
export default function Start() {
  const [status, setStatus] = useState(null)           // null = sprawdzam; { potrzebny, nazwa_lokalu }
  const [samoobsluga, setSamoobsluga] = useState(null) // null = sprawdzam; { enabled, ... }
  const [pokazKreator, setPokazKreator] = useState(false)
  useEffect(() => {
    api('/onboarding/status')
      .then(setStatus)
      .catch(() => setStatus({ potrzebny: false, nazwa_lokalu: 'ten lokal' }))
    api('/online/nowy-lokal/status')
      .then(setSamoobsluga)
      .catch(() => setSamoobsluga({ enabled: false }))
  }, [])

  if (status === null || samoobsluga === null) {
    return (
      <div className="grid min-h-dvh place-items-center bg-bg">
        <Spinner className="h-7 w-7 text-muted" />
      </div>
    )
  }

  // Świeża instancja (operatorska/enterprise, tor --bez-admina) → pełny kreator instancji.
  if (status.potrzebny) return <Onboarding />

  // Wybrano „zakładam własny lokal" → kreator z płatnością (osobna, czysta instancja).
  if (pokazKreator) return <KreatorLokalu planStart={PLAN} />

  const nazwa = status.nazwa_lokalu || 'ten lokal'

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
          {samoobsluga.enabled
            ? <>Nowy lokal dostaje własną, czystą instancję Lokalo — niezależną od lokalu <span className="font-semibold text-ink">{nazwa}</span>, który działa na tej instalacji.</>
            : <>Ta instalacja Lokalo prowadzi już lokal <span className="font-semibold text-ink">{nazwa}</span> — dlatego kreator nowego lokalu nie otworzy się tutaj. Wybierz swoją ścieżkę:</>}
        </p>

        <div className="mt-7 space-y-4">
          {/* Ścieżka 1: własny lokal — kreator z płatnością albo (fallback) kontakt. */}
          <div className="card rounded-2xl border-mint/30 p-5">
            <div className="flex items-start gap-4">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-mint/15 text-mint">
                <Icon name="office" className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-base font-bold text-ink">Zakładam własny lokal</span>
                  {PLAN && samoobsluga.enabled && (
                    <span className="rounded-full bg-mint/20 px-2.5 py-0.5 text-[11px] font-bold text-mint">
                      pakiet {PLAN_ETYKIETA[PLAN]}
                    </span>
                  )}
                </div>

                {samoobsluga.enabled ? (
                  <div className="mt-3">
                    <p className="text-sm leading-relaxed text-muted">
                      <span className="font-semibold text-mint">14 dni pełnego dostępu za darmo, bez karty.</span>{' '}
                      Kilka kroków: e-mail i hasło właściciela, typ lokalu, plan i moduły. System
                      automatycznie postawi Ci własną instancję z gotowym kontem — wejdziesz od razu,
                      logując się e-mailem. Po trialu lokal przechodzi na plan Darmowy (rdzeń działa dalej).
                    </p>
                    <button
                      onClick={() => setPokazKreator(true)}
                      className="mt-4 inline-flex items-center gap-2 rounded-xl bg-mint px-5 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]"
                    >
                      Zacznij 14 dni za darmo <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
                    </button>
                  </div>
                ) : (
                  <div className="mt-1">
                    <p className="text-sm leading-relaxed text-muted">
                      Samoobsługowe zakładanie lokali jest wyłączone na tej instalacji — napisz do nas,
                      a przygotujemy Ci instancję. Kreator (podgląd) pokaże, jak wygląda konfiguracja.
                    </p>
                    <div className="mt-3 flex flex-wrap gap-3">
                      <a
                        href={`mailto:kontakt@grafikpracy.pl?subject=${encodeURIComponent('Nowy lokal na Lokalo')}`}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-mint px-4 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105"
                      >
                        Napisz do nas
                      </a>
                      <a
                        href={`?onboarding${PLAN ? `&plan=${PLAN}` : ''}`}
                        className="inline-flex items-center gap-1.5 text-sm font-semibold text-mint"
                      >
                        Zobacz podgląd kreatora <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
                      </a>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Ścieżka 2: istniejące konto. */}
          <a
            href="?login"
            className="card flex items-start gap-4 rounded-2xl p-5 transition duration-200 hover:border-white/[0.16] active:scale-[0.99]"
          >
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/[0.06] text-muted">
              <Icon name="key" className="h-5 w-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-display text-base font-bold text-ink">Mam już konto</span>
              <span className="mt-1 block text-sm leading-relaxed text-muted">
                Wracasz do panelu lokalu {nazwa}? Zaloguj się e-mailem. (Konto pracownika? Zakłada się
                z linku-zaproszenia od managera.)
              </span>
              <span className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-ink">
                Zaloguj się <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
              </span>
            </span>
          </a>
        </div>

        <a href="?produkt" className="mt-8 text-center text-xs text-muted transition hover:text-ink">
          ← Wróć na stronę Lokalo
        </a>
      </div>
    </div>
  )
}
