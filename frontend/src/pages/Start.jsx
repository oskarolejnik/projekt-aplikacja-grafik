import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { Spinner } from '../components/ui/Spinner'
import Onboarding from './Onboarding'

const fld = 'w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none transition focus:border-mint'

// Pakiet z cennika (?start&plan=pro) → wysyłany przy zakładaniu instancji,
// ląduje od razu w subskrypcji świeżego lokalu.
const PLAN = (() => {
  const p = (new URLSearchParams(window.location.search).get('plan') || '').toLowerCase()
  return ['darmowy', 'basic', 'pro', 'premium'].includes(p) ? p : null
})()
const PLAN_ETYKIETA = { darmowy: 'Darmowy', basic: 'Basic', pro: 'Pro', premium: 'Premium' }

// ?start — brama „Zacznij za darmo" z landingu. Na świeżej instancji (0 użytkowników)
// od razu otwiera kreator lokalu. Na działającej: gdy samoobsługa jest włączona,
// pokazuje KRÓTKI formularz zakładania lokalu (nazwa + e-mail) — pełny kreator
// odpala się dopiero RAZ, na świeżej instancji (feedback: „kreator pojawia się
// taki sam dwa razy — nie chciałbym, żeby tak to wyglądało").
export default function Start() {
  const [status, setStatus] = useState(null)           // null = sprawdzam; { potrzebny, nazwa_lokalu }
  const [samoobsluga, setSamoobsluga] = useState(null) // null = sprawdzam; { enabled, ... }
  useEffect(() => {
    api('/onboarding/status')
      .then(setStatus)
      .catch(() => setStatus({ potrzebny: false, nazwa_lokalu: 'ten lokal' }))
    api('/online/nowy-lokal/status')
      .then(setSamoobsluga)
      .catch(() => setSamoobsluga({ enabled: false }))
  }, [])

  // Krótki formularz samoobsługi.
  const [nazwaLokalu, setNazwaLokalu] = useState('')
  const [email, setEmail] = useState('')
  const [stawianie, setStawianie] = useState(false)
  const [blad, setBlad] = useState(null)
  const [nowy, setNowy] = useState(null)               // {url, nazwa} po sukcesie

  if (status === null || samoobsluga === null) {
    return (
      <div className="grid min-h-dvh place-items-center bg-bg">
        <Spinner className="h-7 w-7 text-muted" />
      </div>
    )
  }

  // Świeża instancja → pełny kreator (konto właściciela + typ lokalu + moduły).
  if (status.potrzebny) return <Onboarding />

  const nazwa = status.nazwa_lokalu || 'ten lokal'

  const utworz = async () => {
    if (nazwaLokalu.trim().length < 3) { setBlad('Podaj nazwę lokalu (min. 3 znaki).'); return }
    setBlad(null)
    setStawianie(true)
    try {
      const r = await api('/online/nowy-lokal', 'POST', {
        nazwa_lokalu: nazwaLokalu.trim(),
        email: email.trim() || null,
        plan: PLAN,
      })
      setNowy(r)
    } catch (e) { setBlad(e.message) } finally { setStawianie(false) }
  }

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
          {/* Ścieżka 1: własny lokal — formularz samoobsługi albo (fallback) podgląd kreatora. */}
          <div className="card rounded-2xl border-mint/30 p-5">
            <div className="flex items-start gap-4">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-mint/15 text-mint">
                <Icon name="office" className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-base font-bold text-ink">Zakładam własny lokal</span>
                  {PLAN && samoobsluga.enabled && !nowy && (
                    <span className="rounded-full bg-mint/20 px-2.5 py-0.5 text-[11px] font-bold text-mint">
                      pakiet {PLAN_ETYKIETA[PLAN]}
                    </span>
                  )}
                </div>

                {samoobsluga.enabled ? (
                  nowy ? (
                    <div className="mt-3">
                      <p className="text-sm leading-relaxed text-muted">
                        Lokal <span className="font-semibold text-ink">„{nowy.nazwa}"</span> jest gotowy — masz
                        własną, czystą instancję. Wejdź i dokończ konfigurację: kreator założy Ci konto właściciela.
                      </p>
                      <a
                        href={nowy.url}
                        className="mt-4 block rounded-xl bg-mint px-4 py-3 text-center text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]"
                      >
                        Wejdź do swojego Lokalo →
                      </a>
                      <p className="mt-2 break-all text-[11px] text-muted/70">{nowy.url}</p>
                    </div>
                  ) : (
                    <div className="mt-3">
                      <p className="text-sm leading-relaxed text-muted">
                        Podaj nazwę — system w pół minuty postawi Ci własną instancję (osobna baza, świeże
                        sekrety). Konto właściciela, typ lokalu i moduły skonfigurujesz już u siebie, w kreatorze.
                      </p>
                      <div className="mt-4 space-y-3">
                        <input
                          value={nazwaLokalu}
                          onChange={(e) => setNazwaLokalu(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') utworz() }}
                          className={fld}
                          placeholder="Nazwa lokalu, np. Bistro Zdrój"
                        />
                        <input
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') utworz() }}
                          className={fld}
                          placeholder="E-mail kontaktowy (opcjonalnie)"
                          autoComplete="email"
                        />
                        {blad && <p className="text-xs font-medium text-danger">{blad}</p>}
                        <button
                          onClick={utworz}
                          disabled={stawianie}
                          className="w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60"
                        >
                          {stawianie ? 'Stawiamy Twój lokal… (do pół minuty)' : 'Utwórz mój lokal'}
                        </button>
                      </div>
                      <a
                        href={`?onboarding${PLAN ? `&plan=${PLAN}` : ''}`}
                        className="mt-3 inline-block text-xs text-muted transition hover:text-ink"
                      >
                        Chcesz najpierw zobaczyć, jak wygląda kreator? Obejrzyj podgląd →
                      </a>
                    </div>
                  )
                ) : (
                  <div className="mt-1">
                    <p className="text-sm leading-relaxed text-muted">
                      Kreator poprowadzi Cię przez start: nazwa lokalu, konto właściciela, typ lokalu i moduły.
                      Kilka minut i panel jest Twój.
                    </p>
                    <a
                      href={`?onboarding${PLAN ? `&plan=${PLAN}` : ''}`}
                      className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-mint"
                    >
                      Otwórz kreator lokalu <Icon name="chevronDown" className="h-4 w-4 -rotate-90" />
                    </a>
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
                Wracasz do panelu lokalu {nazwa}? Zaloguj się jak zwykle. (Konto pracownika? Zakłada się
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
