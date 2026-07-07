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

  return (
    <div className="relative min-h-dvh bg-bg text-ink">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-lg flex-col justify-center px-4 py-10 sm:px-6">
        <div className="mb-8 flex items-center gap-2.5">
          <Logo className="h-8" variant="gradient" />
          <span className="font-display text-lg font-bold">Lokalo</span>
        </div>

        <h1 className="font-display text-2xl font-bold sm:text-3xl" style={{ textWrap: 'balance' }}>
          Od czego zaczynamy?
        </h1>

        <div className="mt-7 space-y-3.5">
          {/* Ścieżka 1: własny lokal — kreator z płatnością (self-service) albo kontakt (fallback). */}
          {samoobsluga.enabled ? (
            <button
              onClick={() => setPokazKreator(true)}
              className="card group flex w-full items-center gap-4 rounded-2xl border-mint/30 p-5 text-left transition duration-200 hover:border-mint/50 active:scale-[0.99]"
            >
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-mint/15 text-mint">
                <Icon name="office" className="h-5 w-5" />
              </span>
              <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-1.5">
                <span className="font-display text-base font-bold text-ink">Zakładam własny lokal</span>
                <span className="rounded-full bg-mint/20 px-2.5 py-0.5 text-[11px] font-bold text-mint">
                  {PLAN ? `pakiet ${PLAN_ETYKIETA[PLAN]}` : '14 dni za darmo'}
                </span>
              </span>
              <Icon name="chevronDown" className="h-4 w-4 -rotate-90 shrink-0 text-muted transition group-hover:text-ink" />
            </button>
          ) : (
            <a
              href={`mailto:kontakt@grafikpracy.pl?subject=${encodeURIComponent('Nowy lokal na Lokalo')}`}
              className="card group flex items-center gap-4 rounded-2xl border-mint/30 p-5 transition duration-200 hover:border-mint/50 active:scale-[0.99]"
            >
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-mint/15 text-mint">
                <Icon name="office" className="h-5 w-5" />
              </span>
              <span className="min-w-0 flex-1 font-display text-base font-bold text-ink">Zakładam własny lokal</span>
              <Icon name="chevronDown" className="h-4 w-4 -rotate-90 shrink-0 text-muted transition group-hover:text-ink" />
            </a>
          )}

          {/* Ścieżka 2: istniejące konto. */}
          <a
            href="?login"
            className="card group flex items-center gap-4 rounded-2xl p-5 transition duration-200 hover:border-white/[0.16] active:scale-[0.99]"
          >
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-white/[0.06] text-muted">
              <Icon name="key" className="h-5 w-5" />
            </span>
            <span className="min-w-0 flex-1 font-display text-base font-bold text-ink">Mam już konto</span>
            <Icon name="chevronDown" className="h-4 w-4 -rotate-90 shrink-0 text-muted transition group-hover:text-ink" />
          </a>
        </div>

        <a href="?produkt" className="mt-8 text-center text-xs text-muted transition hover:text-ink">
          ← Wróć na stronę Lokalo
        </a>
      </div>
    </div>
  )
}
