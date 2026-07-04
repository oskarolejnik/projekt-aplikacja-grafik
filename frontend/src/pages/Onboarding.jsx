import { useEffect, useState } from 'react'
import { api, setToken } from '../lib/api'
import { useToast } from '../components/ui/Toast'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { TYPY, MODULY, KLUCZE_MODULOW, RDZEN, TYP_PO_ID, PRESET_INNY, znormalizujModuly } from './onboarding/typy'

// Kreator zakładania lokalu (tylko pusta instancja — 0 użytkowników). Trzy kroki:
//   1) konto admina + nazwa → POST /api/onboarding/bootstrap (tworzy admina, loguje),
//   2) wybór TYPU restauracji → pre-wypełnia preset modułów,
//   3) dostrój MODUŁY (pełna swoboda) → PUT /api/lokal/config, wejście do panelu.
const fld = 'w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none transition focus:border-mint'
const KROKI = [['konto', 'Konto'], ['typ', 'Typ lokalu'], ['moduly', 'Moduły']]

function Kroki({ krok }) {
  const idx = KROKI.findIndex(([k]) => k === krok)
  return (
    <div className="mb-7 flex items-center justify-center gap-2">
      {KROKI.map(([k, l], i) => (
        <div key={k} className="flex items-center gap-2">
          <span className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold transition ${i <= idx ? 'bg-mint/15 text-mint' : 'text-muted'}`}>
            <span className={`grid h-5 w-5 place-items-center rounded-full text-[11px] ${i < idx ? 'bg-mint text-bg' : i === idx ? 'bg-mint/25 text-mint' : 'bg-white/[0.06] text-muted'}`}>
              {i < idx ? <Icon name="check" className="h-3 w-3" /> : i + 1}
            </span>
            {l}
          </span>
          {i < KROKI.length - 1 && <span className="h-px w-5 bg-line" />}
        </div>
      ))}
    </div>
  )
}

// Mini-podgląd presetu: rząd 6 kropek (aktywne = mięta).
function PresetPreview({ moduly }) {
  return (
    <div className="mt-3 flex items-center gap-1.5">
      {MODULY.map((m) => (
        <span key={m.key} title={m.label} className={`h-1.5 w-1.5 rounded-full ${moduly[m.key] ? 'bg-mint' : 'bg-white/15'}`} />
      ))}
      <span className="ml-1.5 text-[11px] text-muted">{KLUCZE_MODULOW.filter((k) => moduly[k]).length}/6 modułów</span>
    </div>
  )
}

function Toggle({ on, onClick, disabled }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={onClick} disabled={disabled}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? 'bg-mint' : 'bg-white/[0.12]'} ${disabled ? 'opacity-50' : ''}`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  )
}

// Pakiet wybrany na stronie cennika wędruje w URL (?start&plan=pro) — kreator
// pokazuje go w kroku konta i po bootstrapie ustawia tier subskrypcji instancji.
const PLAN_Z_URL = (() => {
  const p = (new URLSearchParams(window.location.search).get('plan') || '').toLowerCase()
  return ['darmowy', 'basic', 'pro', 'premium'].includes(p) ? p : null
})()
const PLAN_NA_TIER = { darmowy: 'free', basic: 'basic', pro: 'pro', premium: 'premium' }
const PLAN_ETYKIETA = { darmowy: 'Darmowy', basic: 'Basic', pro: 'Pro', premium: 'Premium' }

// demo=true (zajęta instancja, wejście przez ?onboarding): kreator działa jako
// PODGLĄD — wszystkie kroki klikalne, zapis wyłączony, finał wyjaśnia, że nowy
// lokal dostaje własną instancję. Na świeżej instancji (demo=false) pełny bootstrap.
export default function Onboarding({ demo = false }) {
  const { toast } = useToast()
  const [krok, setKrok] = useState('konto')
  const [form, setForm] = useState({ nazwa_lokalu: '', login: '', haslo: '' })
  const [busy, setBusy] = useState(false)
  const [wybranyTyp, setWybranyTyp] = useState(null) // id typu lub 'inny'
  const [moduly, setModuly] = useState(PRESET_INNY)
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }))

  const presetWybranego = wybranyTyp === 'inny' ? PRESET_INNY : (TYP_PO_ID[wybranyTyp]?.moduly || PRESET_INNY)
  const zmienione = KLUCZE_MODULOW.some((k) => moduly[k] !== presetWybranego[k])

  // Krok 1 → bootstrap admina.
  const zalozKonto = async () => {
    if (!form.nazwa_lokalu.trim()) { toast('Podaj nazwę lokalu.', 'error'); return }
    if (form.login.trim().length < 5) { toast('Login: min. 5 znaków (litery i cyfry).', 'error'); return }
    if (form.haslo.length < 8) { toast('Hasło: min. 8 znaków (litera + cyfra + znak specjalny).', 'error'); return }
    if (demo) { setKrok('typ'); return }   // podgląd: bez zapisu, idziemy dalej
    setBusy(true)
    try {
      const r = await api('/onboarding/bootstrap', 'POST', {
        login: form.login.trim(), haslo: form.haslo, nazwa_lokalu: form.nazwa_lokalu.trim(),
      })
      setToken(r.access_token)
      // Pakiet z cennika → tier subskrypcji (best-effort; operator może zmienić w Ustawieniach).
      if (PLAN_Z_URL) {
        try { await api('/subskrypcja', 'PUT', { tier: PLAN_NA_TIER[PLAN_Z_URL] }) } catch { /* nie blokuj kreatora */ }
      }
      setKrok('typ')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  // Krok 2 → wybór typu (pre-wypełnia moduły) i przejście do modułów.
  const wybierzTyp = (id) => {
    setWybranyTyp(id)
    setModuly(znormalizujModuly(id === 'inny' ? PRESET_INNY : TYP_PO_ID[id].moduly))
    setKrok('moduly')
  }

  // Kaskada zależności kierunkowo (blindly-normalize faworyzowałby online przy wyłączaniu rezerwacji):
  //  • wyłączenie modułu rezerwacji → gasi widget online,
  //  • włączenie widgetu online → włącza moduł rezerwacji.
  const przelacz = (key) => setModuly((m) => {
    const next = { ...m, [key]: !m[key] }
    if (key === 'modul_rezerwacje' && !next.modul_rezerwacje) next.rezerwacje_online = false
    if (key === 'rezerwacje_online' && next.rezerwacje_online) next.modul_rezerwacje = true
    return next
  })

  // Krok 3 → zapis konfiguracji i wejście.
  const zakoncz = async () => {
    if (demo) { setKrok('gotowe-demo'); return }   // podgląd: ekran podsumowania zamiast zapisu
    setBusy(true)
    try {
      await api('/lokal/config', 'PUT', { typ_lokalu: wybranyTyp === 'inny' ? null : wybranyTyp, ...moduly })
      toast('Lokal skonfigurowany — zapraszamy!', 'success')
      window.location.href = '/'
    } catch (e) { toast(e.message, 'error'); setBusy(false) }
  }

  // Samoobsługa (finał podglądu): jeśli matka ma włączony provisioning, klient
  // zakłada lokal JEDNYM KLIKIEM — system stawia mu świeżą instancję i oddaje link.
  const [samoobsluga, setSamoobsluga] = useState(null)   // null=sprawdzam, {enabled,...}
  const [emailKontakt, setEmailKontakt] = useState('')
  const [stawianie, setStawianie] = useState(false)
  const [nowyLokal, setNowyLokal] = useState(null)        // {url, nazwa} po sukcesie
  useEffect(() => {
    if (krok !== 'gotowe-demo' || samoobsluga !== null) return
    api('/online/nowy-lokal/status').then(setSamoobsluga).catch(() => setSamoobsluga({ enabled: false }))
  }, [krok, samoobsluga])

  const utworzLokal = async () => {
    setStawianie(true)
    try {
      const r = await api('/online/nowy-lokal', 'POST', {
        nazwa_lokalu: form.nazwa_lokalu.trim() || 'Mój lokal',
        email: emailKontakt.trim() || null,
      })
      setNowyLokal(r)
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setStawianie(false)
    }
  }

  const posortowane = [...TYPY].sort((a, b) => (b.popularny ? 1 : 0) - (a.popularny ? 1 : 0))

  return (
    <div className="relative min-h-dvh bg-bg px-4 py-10">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto w-full max-w-3xl">
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-9" variant="gradient" />
          <div>
            <h1 className="font-display text-xl font-bold text-ink">Kreator lokalu</h1>
            <p className="text-xs text-muted">Skonfiguruj system pod swoją knajpę w kilka kroków.</p>
          </div>
        </div>

        {demo && (
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-lemon/30 bg-lemon/10 px-4 py-3">
            <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-lemon" />
            <p className="text-xs leading-relaxed text-muted">
              <span className="font-semibold text-ink">Podgląd kreatora.</span> Ta instalacja prowadzi już
              lokal — kroki są klikalne, ale nic się nie zapisze. Nowy lokal dostaje własną, czystą instancję.
            </p>
          </div>
        )}

        <Kroki krok={krok} />

        {/* KROK 1 — konto */}
        {krok === 'konto' && (
          <div className="mx-auto max-w-md">
            <div className="card p-6 sm:p-8">
              {PLAN_Z_URL && (
                <div className="mb-5 flex items-center justify-between rounded-xl bg-mint/10 px-4 py-2.5">
                  <span className="text-xs font-semibold text-muted">Wybrany pakiet</span>
                  <span className="rounded-full bg-mint/20 px-3 py-1 text-xs font-bold text-mint">
                    {PLAN_ETYKIETA[PLAN_Z_URL]}
                  </span>
                </div>
              )}
              <div className="space-y-3">
                <label className="block text-xs font-semibold text-muted">Nazwa lokalu
                  <input value={form.nazwa_lokalu} onChange={(e) => set('nazwa_lokalu', e.target.value)} className={fld} placeholder="Moja Restauracja" /></label>
                <label className="block text-xs font-semibold text-muted">Login administratora
                  <input value={form.login} onChange={(e) => set('login', e.target.value)} className={fld} placeholder="min. 5 znaków, litery i cyfry" /></label>
                <label className="block text-xs font-semibold text-muted">Hasło
                  <input type="password" value={form.haslo} onChange={(e) => set('haslo', e.target.value)} className={fld} placeholder="min. 8 znaków: litera + cyfra + znak specjalny" /></label>
              </div>
              <button onClick={zalozKonto} disabled={busy}
                className="mt-5 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.99] disabled:opacity-60">
                {busy ? 'Zakładam…' : 'Dalej — wybór typu lokalu'}
              </button>
              <p className="mt-3 text-center text-xs text-muted/70">
                {demo ? 'Podgląd — dane nie zostaną zapisane.' : 'Ten kreator pojawia się tylko na nowej, pustej instancji.'}
              </p>
            </div>
          </div>
        )}

        {/* KROK 2 — typ lokalu */}
        {krok === 'typ' && (
          <div>
            <p className="mb-4 text-center text-sm text-muted">Wybierz najbliższy typ — dobierzemy sensowne moduły, które i tak dostroisz w następnym kroku.</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {posortowane.map((t) => (
                <button key={t.id} onClick={() => wybierzTyp(t.id)}
                  className="group flex flex-col rounded-2xl border border-line bg-surface-grad p-4 text-left shadow-soft transition hover:-translate-y-0.5 hover:border-mint/50">
                  <div className="flex items-center justify-between">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-surface-2 text-mint transition group-hover:bg-mint/15">
                      <Icon name={t.ikona} className="h-5 w-5" />
                    </span>
                    {t.popularny && <span className="rounded-full bg-mint/15 px-2 py-0.5 text-[10px] font-semibold text-mint">Częsty wybór</span>}
                  </div>
                  <h3 className="mt-3 font-display text-base font-semibold text-ink">{t.nazwa}</h3>
                  <p className="mt-1 flex-1 text-xs leading-relaxed text-muted">{t.opis}</p>
                  <PresetPreview moduly={t.moduly} />
                </button>
              ))}
              {/* Inny / od zera */}
              <button onClick={() => wybierzTyp('inny')}
                className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-surface-2/30 p-4 text-center transition hover:border-mint/50 hover:text-ink">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-surface-2 text-muted"><Icon name="plus" className="h-5 w-5" /></span>
                <h3 className="mt-3 font-display text-base font-semibold text-ink">Inny / od zera</h3>
                <p className="mt-1 text-xs text-muted">Zacznij od uniwersalnego presetu i ustaw wszystko po swojemu.</p>
              </button>
            </div>
          </div>
        )}

        {/* KROK 3 — moduły */}
        {krok === 'moduly' && (
          <div className="mx-auto max-w-xl">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted">
                Dostrój moduły dla: <span className="font-semibold text-ink">{wybranyTyp === 'inny' ? 'Twój lokal' : TYP_PO_ID[wybranyTyp]?.nazwa}</span>. Możesz zmienić wszystko.
              </p>
              {zmienione && (
                <button onClick={() => setModuly(znormalizujModuly(presetWybranego))}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs font-semibold text-muted transition hover:text-ink">
                  <Icon name="refresh" className="h-3.5 w-3.5" /> Przywróć preset
                </button>
              )}
            </div>

            <div className="card divide-y divide-line">
              {MODULY.map((m) => {
                const zaleznyOff = m.wymaga && !moduly[m.wymaga]
                return (
                  <div key={m.key} className={`flex items-start gap-3 p-4 ${m.wymaga ? 'pl-6' : ''}`}>
                    <span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl ${moduly[m.key] ? 'bg-mint/15 text-mint' : 'bg-surface-2 text-muted'}`}>
                      <Icon name={m.ikona} className="h-5 w-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-bold text-ink">{m.label}</div>
                      <div className="text-xs leading-relaxed text-muted">{m.opis}</div>
                      {zaleznyOff && <div className="mt-1 text-[11px] text-lemon">Włączenie automatycznie doda też moduł rezerwacji.</div>}
                    </div>
                    <Toggle on={!!moduly[m.key]} onClick={() => przelacz(m.key)} />
                  </div>
                )
              })}
            </div>

            <div className="mt-4 rounded-xl border border-line bg-surface-2/30 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted">Zawsze włączone (rdzeń)</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {RDZEN.map((r) => (
                  <span key={r} className="inline-flex items-center gap-1 rounded-full bg-white/[0.04] px-2.5 py-1 text-[11px] text-muted">
                    <Icon name="check" className="h-3 w-3 text-mint" /> {r}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-5 flex items-center justify-between gap-3">
              <button onClick={() => setKrok('typ')} className="rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-muted transition hover:text-ink">
                ← Zmień typ
              </button>
              <button onClick={zakoncz} disabled={busy}
                className="rounded-xl bg-mint px-6 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60">
                {busy ? 'Zapisuję…' : demo ? 'Zobacz podsumowanie' : 'Zapisz i wejdź do panelu'}
              </button>
            </div>
          </div>
        )}

        {/* FINAŁ PODGLĄDU (tylko demo): samoobsługa — system SAM stawia lokal.
            (Mailto zostaje wyłącznie jako fallback, gdy operator wyłączył provisioning.) */}
        {krok === 'gotowe-demo' && (
          <div className="mx-auto max-w-md">
            <div className="card p-6 text-center sm:p-8">
              {nowyLokal ? (
                <>
                  <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-mint/15">
                    <Icon name="check" className="h-6 w-6 text-mint" />
                  </span>
                  <h2 className="mt-4 font-display text-xl font-bold text-ink">
                    Lokal „{nowyLokal.nazwa}" jest gotowy
                  </h2>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    Postawiliśmy Twoją własną, czystą instancję. Wejdź i dokończ konfigurację —
                    kreator założy Ci konto właściciela{PLAN_Z_URL ? ` (pakiet ${PLAN_ETYKIETA[PLAN_Z_URL]})` : ''}.
                  </p>
                  <a
                    href={nowyLokal.url}
                    className="mt-6 block rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]"
                  >
                    Wejdź do swojego Lokalo →
                  </a>
                  <p className="mt-3 break-all text-[11px] text-muted/70">{nowyLokal.url}</p>
                </>
              ) : samoobsluga?.enabled ? (
                <>
                  <h2 className="font-display text-xl font-bold text-ink">
                    Załóż lokal „{form.nazwa_lokalu || 'Twój lokal'}" teraz
                  </h2>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    Jedno kliknięcie: system automatycznie stawia Twoją własną instancję
                    (osobna baza, świeże sekrety) i przenosi Cię do prawdziwego kreatora.
                  </p>
                  <input
                    value={emailKontakt}
                    onChange={(e) => setEmailKontakt(e.target.value)}
                    className={`${fld} mt-5`}
                    placeholder="E-mail kontaktowy (opcjonalnie)"
                    autoComplete="email"
                  />
                  <button
                    onClick={utworzLokal}
                    disabled={stawianie}
                    className="mt-4 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60"
                  >
                    {stawianie ? 'Stawiamy Twój lokal… (do pół minuty)' : 'Utwórz mój lokal'}
                  </button>
                </>
              ) : samoobsluga === null ? (
                <p className="py-8 text-sm text-muted">Sprawdzam dostępność samoobsługi…</p>
              ) : (
                <>
                  <h2 className="font-display text-xl font-bold text-ink">
                    Tak wygląda start lokalu „{form.nazwa_lokalu || 'Twój lokal'}"
                  </h2>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    Samoobsługowe zakładanie lokali jest wyłączone na tej instalacji —
                    napisz, a przygotujemy Ci instancję.
                  </p>
                  <a
                    href={`mailto:kontakt@grafikpracy.pl?subject=${encodeURIComponent('Nowy lokal na Lokalo')}`}
                    className="mt-6 block rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]"
                  >
                    Napisz do nas
                  </a>
                </>
              )}
              <a href="?produkt" className="mt-3 block text-xs text-muted transition hover:text-ink">
                ← Wróć na stronę Lokalo
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
