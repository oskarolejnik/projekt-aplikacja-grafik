import { useState } from 'react'
import { api } from '../lib/api'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { TYPY, MODULY, KLUCZE_MODULOW, RDZEN, TYP_PO_ID, PRESET_INNY, znormalizujModuly } from './onboarding/typy'

// Kreator zakładania lokalu Z PŁATNOŚCIĄ (instancja-matka). Zbiera dane właściciela + wybór
// typu/modułów + plan, przechodzi do checkoutu, a DOPIERO po opłaceniu backend stawia instancję
// z gotowym adminem (logowanie e-mailem) i aktywną subskrypcją → redirect na ?login.
// Kroki: konto → typ → moduły → plan → checkout → (stawianie…). Reużywa taksonomii z onboarding/typy.

const fld = 'w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none transition focus:border-mint'
const emailOk = (e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test((e || '').trim())

// Ceny netto/mies. (spójne z backend/cennik.py); brutto liczy backend i pokazuje na checkoucie.
const PLANY = [
  { id: 'darmowy', nazwa: 'Darmowy', netto: 0, opis: 'Auto-grafik, RCP → wypłaty, prognoza obsady — na dobry start.' },
  { id: 'basic', nazwa: 'Basic', netto: 99, opis: 'Rozliczenia kasowe dnia z alertami anomalii.' },
  { id: 'pro', nazwa: 'Pro', netto: 199, opis: 'Rezerwacje, CRM gości, pulpit KPI i integracja POS.', polecany: true },
  { id: 'premium', nazwa: 'Premium', netto: 349, opis: 'Wszystko z Pro + zgodność lokalu i pełne wsparcie.' },
]
const PLAN_PO_ID = Object.fromEntries(PLANY.map((p) => [p.id, p]))

function Toggle({ on, onClick }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={onClick}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? 'bg-mint' : 'bg-white/[0.12]'}`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  )
}

const KROKI = [['konto', 'Konto'], ['typ', 'Typ'], ['moduly', 'Moduły'], ['plan', 'Plan'], ['checkout', 'Płatność']]

function Kroki({ krok }) {
  const idx = KROKI.findIndex(([k]) => k === krok || (krok === 'stawianie' && k === 'checkout'))
  return (
    <div className="mb-7 flex flex-wrap items-center justify-center gap-2">
      {KROKI.map(([k, l], i) => (
        <span key={k} className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition ${i <= idx ? 'bg-mint/15 text-mint' : 'text-muted'}`}>
          <span className={`grid h-5 w-5 place-items-center rounded-full text-[11px] ${i < idx ? 'bg-mint text-bg' : i === idx ? 'bg-mint/25 text-mint' : 'bg-white/[0.06] text-muted'}`}>
            {i < idx ? <Icon name="check" className="h-3 w-3" /> : i + 1}
          </span>
          {l}
        </span>
      ))}
    </div>
  )
}

export default function KreatorLokalu({ planStart = null }) {
  const [krok, setKrok] = useState('konto')
  const [form, setForm] = useState({ email: '', haslo: '', nazwa: '' })
  const [wybranyTyp, setWybranyTyp] = useState(null)
  const [moduly, setModuly] = useState(PRESET_INNY)
  const [plan, setPlan] = useState(PLAN_PO_ID[planStart] ? planStart : null)
  const [zam, setZam] = useState(null)              // {external_id, brutto, plan} z /rejestracja
  const [busy, setBusy] = useState(false)
  const [blad, setBlad] = useState(null)
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }))

  const przelacz = (key) => setModuly((m) => {
    const next = { ...m, [key]: !m[key] }
    if (key === 'modul_rezerwacje' && !next.modul_rezerwacje) next.rezerwacje_online = false
    if (key === 'rezerwacje_online' && next.rezerwacje_online) next.modul_rezerwacje = true
    return next
  })

  const dalejKonto = () => {
    if (form.nazwa.trim().length < 3) { setBlad('Podaj nazwę lokalu (min. 3 znaki).'); return }
    if (!emailOk(form.email)) { setBlad('Podaj prawidłowy adres e-mail — nim się zalogujesz.'); return }
    if (form.haslo.length < 8) { setBlad('Hasło: min. 8 znaków (litera + cyfra + znak specjalny).'); return }
    setBlad(null); setKrok('typ')
  }
  const wybierzTyp = (id) => {
    setWybranyTyp(id)
    setModuly(znormalizujModuly(id === 'inny' ? PRESET_INNY : TYP_PO_ID[id].moduly))
    setKrok('moduly')
  }

  // Krok „plan" → utwórz rejestrację i przejdź do checkoutu.
  const doPlatnosci = async () => {
    if (!plan) { setBlad('Wybierz pakiet.'); return }
    setBlad(null); setBusy(true)
    try {
      const r = await api('/online/rejestracja', 'POST', {
        email: form.email.trim(), haslo: form.haslo, nazwa_lokalu: form.nazwa.trim(),
        plan, typ_lokalu: wybranyTyp === 'inny' ? null : wybranyTyp,
        moduly: { typ_lokalu: wybranyTyp === 'inny' ? null : wybranyTyp, ...moduly },
      })
      setZam(r); setKrok('checkout')
    } catch (e) { setBlad(e.message) } finally { setBusy(false) }
  }

  // Checkout (sandbox) → opłać → backend stawia instancję z adminem → redirect na ?login.
  const zaplac = async () => {
    setBlad(null); setKrok('stawianie')
    try {
      const r = await api(`/online/rejestracja/${zam.external_id}/oplac`, 'POST')
      window.location.href = r.url   // pełne przeładowanie na świeżą instancję (?login)
    } catch (e) { setBlad(e.message); setKrok('checkout') }
  }

  const posortowane = [...TYPY].sort((a, b) => (b.popularny ? 1 : 0) - (a.popularny ? 1 : 0))

  return (
    <div className="relative min-h-dvh bg-bg px-4 py-10 text-ink">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto w-full max-w-3xl">
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-9" variant="gradient" />
          <div>
            <h1 className="font-display text-xl font-bold text-ink">Zakładasz swój lokal</h1>
            <p className="text-xs text-muted">Konto powstaje po opłaceniu — instancja staje sama.</p>
          </div>
        </div>

        <Kroki krok={krok} />

        {/* KROK 1 — konto właściciela */}
        {krok === 'konto' && (
          <div className="mx-auto max-w-md">
            <div className="card p-6 sm:p-8">
              <div className="space-y-3">
                <label className="block text-xs font-semibold text-muted">Nazwa lokalu
                  <input value={form.nazwa} onChange={(e) => set('nazwa', e.target.value)} className={fld} placeholder="np. Bistro Zdrój" /></label>
                <label className="block text-xs font-semibold text-muted">E-mail właściciela
                  <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} autoComplete="email" className={fld} placeholder="np. jan@lokal.pl — nim się zalogujesz" /></label>
                <label className="block text-xs font-semibold text-muted">Hasło
                  <input type="password" value={form.haslo} onChange={(e) => set('haslo', e.target.value)} autoComplete="new-password" className={fld} placeholder="min. 8 znaków: litera + cyfra + znak specjalny" /></label>
              </div>
              {blad && <p className="mt-3 text-xs font-medium text-danger">{blad}</p>}
              <button onClick={dalejKonto}
                className="mt-5 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.99]">
                Dalej — typ lokalu
              </button>
            </div>
          </div>
        )}

        {/* KROK 2 — typ */}
        {krok === 'typ' && (
          <div>
            <p className="mb-4 text-center text-sm text-muted">Wybierz najbliższy typ — dobierzemy moduły, które i tak dostroisz w następnym kroku.</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {posortowane.map((t) => (
                <button key={t.id} onClick={() => wybierzTyp(t.id)}
                  className="group flex flex-col rounded-2xl border border-line bg-surface-grad p-4 text-left shadow-soft transition hover:-translate-y-0.5 hover:border-mint/50">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-surface-2 text-mint transition group-hover:bg-mint/15">
                    <Icon name={t.ikona} className="h-5 w-5" />
                  </span>
                  <h3 className="mt-3 font-display text-base font-semibold text-ink">{t.nazwa}</h3>
                  <p className="mt-1 flex-1 text-xs leading-relaxed text-muted">{t.opis}</p>
                </button>
              ))}
              <button onClick={() => wybierzTyp('inny')}
                className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-surface-2/30 p-4 text-center transition hover:border-mint/50 hover:text-ink">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-surface-2 text-muted"><Icon name="plus" className="h-5 w-5" /></span>
                <h3 className="mt-3 font-display text-base font-semibold text-ink">Inny / od zera</h3>
                <p className="mt-1 text-xs text-muted">Uniwersalny preset — ustaw wszystko po swojemu.</p>
              </button>
            </div>
            <button onClick={() => setKrok('konto')} className="mt-5 text-sm font-semibold text-muted transition hover:text-ink">← Wróć</button>
          </div>
        )}

        {/* KROK 3 — moduły */}
        {krok === 'moduly' && (
          <div className="mx-auto max-w-xl">
            <p className="mb-4 text-sm text-muted">
              Dostrój moduły dla: <span className="font-semibold text-ink">{wybranyTyp === 'inny' ? 'Twój lokal' : TYP_PO_ID[wybranyTyp]?.nazwa}</span>. Możesz zmienić wszystko.
            </p>
            <div className="card divide-y divide-line">
              {MODULY.map((m) => (
                <div key={m.key} className={`flex items-start gap-3 p-4 ${m.wymaga ? 'pl-6' : ''}`}>
                  <span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl ${moduly[m.key] ? 'bg-mint/15 text-mint' : 'bg-surface-2 text-muted'}`}>
                    <Icon name={m.ikona} className="h-5 w-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-bold text-ink">{m.label}</div>
                    <div className="text-xs leading-relaxed text-muted">{m.opis}</div>
                  </div>
                  <Toggle on={!!moduly[m.key]} onClick={() => przelacz(m.key)} />
                </div>
              ))}
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
              <button onClick={() => setKrok('typ')} className="rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-muted transition hover:text-ink">← Zmień typ</button>
              <button onClick={() => setKrok('plan')} className="rounded-xl bg-mint px-6 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]">Dalej — plan</button>
            </div>
          </div>
        )}

        {/* KROK 4 — plan */}
        {krok === 'plan' && (
          <div className="mx-auto max-w-xl">
            <p className="mb-4 text-center text-sm text-muted">Wybierz pakiet — zmienisz go w każdej chwili w Ustawieniach.</p>
            <div className="space-y-3">
              {PLANY.map((p) => {
                const on = plan === p.id
                return (
                  <button key={p.id} onClick={() => { setPlan(p.id); setBlad(null) }}
                    className={`flex w-full items-center gap-4 rounded-2xl border p-4 text-left transition ${on ? 'border-mint bg-mint/[0.06]' : 'border-line bg-surface hover:border-mint/40'}`}>
                    <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border ${on ? 'border-mint bg-mint text-bg' : 'border-line text-transparent'}`}>
                      <Icon name="check" className="h-3.5 w-3.5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="font-display text-base font-bold text-ink">{p.nazwa}</span>
                        {p.polecany && <span className="rounded-full bg-mint/15 px-2 py-0.5 text-[10px] font-semibold text-mint">Polecany</span>}
                      </span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-muted">{p.opis}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="font-display text-lg font-bold text-ink">{p.netto === 0 ? '0 zł' : `${p.netto} zł`}</span>
                      <span className="block text-[11px] text-muted">{p.netto === 0 ? 'na zawsze' : 'netto / mies.'}</span>
                    </span>
                  </button>
                )
              })}
            </div>
            {blad && <p className="mt-3 text-center text-xs font-medium text-danger">{blad}</p>}
            <div className="mt-5 flex items-center justify-between gap-3">
              <button onClick={() => setKrok('moduly')} className="rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-muted transition hover:text-ink">← Moduły</button>
              <button onClick={doPlatnosci} disabled={busy}
                className="rounded-xl bg-mint px-6 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60">
                {busy ? 'Chwila…' : 'Przejdź do płatności →'}
              </button>
            </div>
          </div>
        )}

        {/* KROK 5 — checkout (sandbox) */}
        {krok === 'checkout' && zam && (
          <div className="mx-auto max-w-md">
            <div className="card p-6 sm:p-8">
              <h2 className="font-display text-lg font-bold text-ink">Podsumowanie</h2>
              <dl className="mt-4 space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-muted">Lokal</dt><dd className="font-semibold text-ink">{form.nazwa.trim()}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Właściciel (login)</dt><dd className="font-semibold text-ink">{form.email.trim()}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Pakiet</dt><dd className="font-semibold text-ink">{PLAN_PO_ID[zam.plan]?.nazwa || zam.plan}</dd></div>
                <div className="mt-2 flex justify-between border-t border-line pt-3 text-base">
                  <dt className="font-semibold text-ink">Do zapłaty</dt>
                  <dd className="font-display font-bold text-mint">{Number(zam.brutto).toFixed(2)} zł</dd>
                </div>
                <p className="text-[11px] text-muted/70">cena brutto (z VAT) za pierwszy miesiąc</p>
              </dl>
              {blad && <p className="mt-3 text-xs font-medium text-danger">{blad}</p>}
              <button onClick={zaplac}
                className="mt-5 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]">
                {zam.provider === 'sandbox' ? 'Zapłać (tryb testowy) i utwórz lokal' : 'Zapłać i utwórz lokal'}
              </button>
              <p className="mt-3 text-center text-[11px] text-muted/70">
                Konto właściciela i instancja powstaną automatycznie po opłaceniu.
              </p>
              <button onClick={() => setKrok('plan')} className="mt-2 w-full text-center text-xs text-muted transition hover:text-ink">← Zmień plan</button>
            </div>
          </div>
        )}

        {/* Stawianie instancji (po opłaceniu) */}
        {krok === 'stawianie' && (
          <div className="mx-auto max-w-md">
            <div className="card p-8 text-center">
              <span className="mx-auto grid h-12 w-12 animate-pulse place-items-center rounded-full bg-mint/15">
                <Icon name="office" className="h-6 w-6 text-mint" />
              </span>
              <h2 className="mt-4 font-display text-xl font-bold text-ink">Stawiamy Twój lokal…</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Tworzymy osobną instancję (własna baza, świeże sekrety) i konto właściciela.
                Za chwilę przeniesiemy Cię do logowania — to potrwa do pół minuty.
              </p>
            </div>
          </div>
        )}

        <a href="?produkt" className="mt-8 block text-center text-xs text-muted transition hover:text-ink">← Wróć na stronę Lokalo</a>
      </div>
    </div>
  )
}
