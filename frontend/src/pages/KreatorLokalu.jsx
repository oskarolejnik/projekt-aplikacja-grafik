import { useState } from 'react'
import { api } from '../lib/api'
import { Logo } from '../components/Logo'
import { Icon } from '../lib/icons'
import { TYPY, MODULY, RDZEN, TYP_PO_ID, PRESET_INNY, znormalizujModuly } from './onboarding/typy'

// Kreator zakładania lokalu. Kolejność: konto → typ → plan → moduły → (karta) → start.
// Darmowy: instancja od razu, bez karty. Płatny (Basic/Pro/Premium): 14 dni za darmo, ale KARTA
// wymagana — obciążamy dopiero po 14 dniach (auto-odnowienie), jedna karta = jeden trial.
// Świadomie MAŁO tekstu: same wybory, wartość jako mikro-etykiety, nie akapity.

const fld = 'w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none transition focus:border-mint'
const emailOk = (e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test((e || '').trim())

// Lustro backendu (cennik.MODUL_MIN_TIER) — moduł → najniższy plan, który go odblokowuje.
const MODUL_MIN_TIER = {
  modul_rozliczenia: 'basic', modul_rezerwacje: 'pro', rezerwacje_online: 'pro',
  modul_pos: 'pro', modul_imprezy: 'premium', modul_sprzatanie: 'premium',
}
const POZIOM = { free: 0, basic: 1, pro: 2, premium: 3, enterprise: 4 }
const modulDozwolony = (tier, key) => POZIOM[MODUL_MIN_TIER[key] || 'free'] <= POZIOM[tier || 'free']
const ETYKIETA_PLANU = { basic: 'Basic', pro: 'Pro', premium: 'Premium' }

// Ceny netto/mies. (spójne z backend/cennik.py).
const PLANY = [
  { id: 'darmowy', tier: 'free', nazwa: 'Darmowy', netto: 0, opis: 'Rdzeń: grafik, RCP → wypłaty, prognoza obsady.' },
  { id: 'basic', tier: 'basic', nazwa: 'Basic', netto: 99, opis: 'Rdzeń + rozliczenia kasowe dnia.' },
  { id: 'pro', tier: 'pro', nazwa: 'Pro', netto: 199, opis: 'Rezerwacje, CRM gości, pulpit, POS.', polecany: true },
  { id: 'premium', tier: 'premium', nazwa: 'Premium', netto: 349, opis: 'Pro + imprezy, sprzątanie, zgodność.' },
]
const PLAN_PO_ID = Object.fromEntries(PLANY.map((p) => [p.id, p]))

function Toggle({ on, onClick, disabled }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={onClick} disabled={disabled}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${on ? 'bg-mint' : 'bg-white/[0.12]'} ${disabled ? 'opacity-40' : ''}`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  )
}

const KROKI = [['konto', 'Konto'], ['typ', 'Typ'], ['plan', 'Plan'], ['moduly', 'Moduły'], ['start', 'Start']]

function Kroki({ krok }) {
  const map = { karta: 'start', stawianie: 'start' }
  const cur = map[krok] || krok
  const idx = KROKI.findIndex(([k]) => k === cur)
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
  const [wybor, setWybor] = useState(PLAN_PO_ID[planStart] ? planStart : 'pro')
  const [karta, setKarta] = useState({ numer: '', exp: '', cvc: '' })
  const [busy, setBusy] = useState(false)
  const [blad, setBlad] = useState(null)
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }))
  const setK = (k, v) => setKarta((s) => ({ ...s, [k]: v }))

  const plan = PLAN_PO_ID[wybor] || PLAN_PO_ID.pro
  const platny = plan.tier !== 'free'
  const dozwolony = (key) => modulDozwolony(plan.tier, key)

  const przelacz = (key) => {
    if (!dozwolony(key)) return
    setModuly((m) => {
      const next = { ...m, [key]: !m[key] }
      if (key === 'modul_rezerwacje' && !next.modul_rezerwacje) next.rezerwacje_online = false
      if (key === 'rezerwacje_online' && next.rezerwacje_online) next.modul_rezerwacje = true
      return next
    })
  }

  const dalejKonto = () => {
    if (form.nazwa.trim().length < 3) { setBlad('Podaj nazwę lokalu (min. 3 znaki).'); return }
    if (!emailOk(form.email)) { setBlad('Podaj prawidłowy e-mail — nim się zalogujesz.'); return }
    if (form.haslo.length < 8) { setBlad('Hasło: min. 8 znaków (litera + cyfra + znak specjalny).'); return }
    setBlad(null); setKrok('typ')
  }
  const wybierzTyp = (id) => {
    setWybranyTyp(id)
    setModuly(znormalizujModuly(id === 'inny' ? PRESET_INNY : TYP_PO_ID[id].moduly))
    setKrok('plan')
  }
  const doModulow = () => {
    setModuly((m) => {
      const next = { ...m }
      for (const mm of MODULY) if (!dozwolony(mm.key)) next[mm.key] = false
      return znormalizujModuly(next)
    })
    setKrok('moduly')
  }

  const wspolne = () => ({
    email: form.email.trim(), haslo: form.haslo, nazwa_lokalu: form.nazwa.trim(),
    typ_lokalu: wybranyTyp === 'inny' ? null : wybranyTyp,
    moduly: { typ_lokalu: wybranyTyp === 'inny' ? null : wybranyTyp, ...moduly },
  })

  // Z kroku „moduły": Darmowy → stawiamy od razu; płatny → krok karty.
  const dalejZModulow = async () => {
    if (platny) { setBlad(null); setKrok('karta'); return }
    setBlad(null); setBusy(true); setKrok('stawianie')
    try {
      const r = await api('/online/rejestracja', 'POST', { ...wspolne(), plan: 'darmowy' })
      window.location.href = r.url
    } catch (e) { setBlad(e.message); setKrok('moduly') } finally { setBusy(false) }
  }

  // Krok karty (plan płatny): 14 dni za darmo, obciążenie po trialu. Sandbox: karta testowa.
  const rozpocznijTrial = async () => {
    const numer = karta.numer.replace(/\s/g, '')
    const m = karta.exp.match(/^\s*(\d{1,2})\s*\/\s*(\d{2,4})\s*$/)
    if (numer.replace(/\D/g, '').length < 12 || !m || karta.cvc.replace(/\D/g, '').length < 3) {
      setBlad('Sprawdź dane karty: numer, ważność MM/RR i kod CVC.'); return
    }
    setBlad(null); setBusy(true); setKrok('stawianie')
    try {
      const r = await api('/online/rejestracja', 'POST', {
        ...wspolne(), plan: wybor,
        karta: { numer, exp_miesiac: Number(m[1]), exp_rok: Number(m[2]), cvc: karta.cvc.trim() },
      })
      window.location.href = r.url
    } catch (e) { setBlad(e.message); setKrok('karta') } finally { setBusy(false) }
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
            <p className="text-xs text-muted">Plany płatne: 14 dni za darmo.</p>
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
                  <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} autoComplete="email" className={fld} placeholder="jan@lokal.pl — nim się zalogujesz" /></label>
                <label className="block text-xs font-semibold text-muted">Hasło
                  <input type="password" value={form.haslo} onChange={(e) => set('haslo', e.target.value)} autoComplete="new-password" className={fld} placeholder="min. 8 znaków" /></label>
              </div>
              {blad && <p className="mt-3 text-xs font-medium text-danger">{blad}</p>}
              <button onClick={dalejKonto}
                className="mt-5 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.99]">
                Dalej
              </button>
            </div>
          </div>
        )}

        {/* KROK 2 — typ */}
        {krok === 'typ' && (
          <div>
            <p className="mb-4 text-center text-sm text-muted">Wybierz typ lokalu.</p>
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
              </button>
            </div>
            <button onClick={() => setKrok('konto')} className="mt-5 text-sm font-semibold text-muted transition hover:text-ink">← Wróć</button>
          </div>
        )}

        {/* KROK 3 — plan */}
        {krok === 'plan' && (
          <div className="mx-auto max-w-xl">
            <div className="space-y-3">
              {PLANY.map((p) => {
                const on = wybor === p.id
                return (
                  <button key={p.id} onClick={() => setWybor(p.id)}
                    className={`flex w-full items-center gap-4 rounded-2xl border p-4 text-left transition ${on ? 'border-mint bg-mint/[0.06]' : 'border-line bg-surface hover:border-mint/40'}`}>
                    <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border ${on ? 'border-mint bg-mint text-bg' : 'border-line text-transparent'}`}>
                      <Icon name="check" className="h-3.5 w-3.5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-display text-base font-bold text-ink">{p.nazwa}</span>
                        {p.polecany && <span className="rounded-full bg-mint/15 px-2 py-0.5 text-[10px] font-semibold text-mint">Polecany</span>}
                        {p.tier !== 'free' && <span className="rounded-full bg-mint/20 px-2 py-0.5 text-[10px] font-bold text-mint">14 dni gratis</span>}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted">{p.opis}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="font-display text-lg font-bold text-ink">{p.netto === 0 ? '0 zł' : `${p.netto} zł`}</span>
                      <span className="block text-[11px] text-muted">{p.netto === 0 ? 'na zawsze' : '/mies.'}</span>
                    </span>
                  </button>
                )
              })}
            </div>
            <p className="mt-3 text-center text-[11px] text-muted">
              Plany płatne: 14 dni za darmo, potem automatycznie. Anuluj w każdej chwili.
            </p>
            <div className="mt-5 flex items-center justify-between gap-3">
              <button onClick={() => setKrok('typ')} className="rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-muted transition hover:text-ink">← Typ</button>
              <button onClick={doModulow} className="rounded-xl bg-mint px-6 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]">Dalej</button>
            </div>
          </div>
        )}

        {/* KROK 4 — moduły (zależne od planu) */}
        {krok === 'moduly' && (
          <div className="mx-auto max-w-xl">
            <p className="mb-4 text-sm text-muted">
              Moduły w planie <span className="font-semibold text-ink">{plan.nazwa}</span>.
              {platny && ' Wyższe odblokujesz podnosząc plan.'}
            </p>
            <div className="card divide-y divide-line">
              {MODULY.map((m) => {
                const ok = dozwolony(m.key)
                return (
                  <div key={m.key} className={`flex items-start gap-3 p-4 ${m.wymaga ? 'pl-6' : ''} ${ok ? '' : 'opacity-70'}`}>
                    <span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl ${moduly[m.key] && ok ? 'bg-mint/15 text-mint' : 'bg-surface-2 text-muted'}`}>
                      <Icon name={ok ? m.ikona : 'key'} className="h-5 w-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm font-bold text-ink">
                        {m.label}
                        {!ok && <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] font-semibold text-muted">{ETYKIETA_PLANU[MODUL_MIN_TIER[m.key]]}+</span>}
                      </div>
                      <div className="text-xs leading-relaxed text-muted">{m.opis}</div>
                    </div>
                    <Toggle on={!!moduly[m.key] && ok} onClick={() => przelacz(m.key)} disabled={!ok} />
                  </div>
                )
              })}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-1.5 rounded-xl border border-line bg-surface-2/30 px-4 py-3">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Zawsze w cenie:</span>
              {RDZEN.map((r) => (
                <span key={r} className="text-[11px] text-muted">· {r}</span>
              ))}
            </div>
            {blad && <p className="mt-3 text-xs font-medium text-danger">{blad}</p>}
            <div className="mt-5 flex items-center justify-between gap-3">
              <button onClick={() => setKrok('plan')} className="rounded-xl border border-line px-4 py-2.5 text-sm font-semibold text-muted transition hover:text-ink">← Plan</button>
              <button onClick={dalejZModulow} disabled={busy}
                className="rounded-xl bg-mint px-6 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60">
                {busy ? 'Chwila…' : platny ? 'Dalej — karta' : 'Utwórz lokal →'}
              </button>
            </div>
          </div>
        )}

        {/* KROK 5 — karta (tylko plan płatny): 14 dni za darmo, obciążenie po trialu */}
        {krok === 'karta' && (
          <div className="mx-auto max-w-md">
            <div className="card p-6 sm:p-8">
              <h2 className="font-display text-lg font-bold text-ink">14 dni za darmo</h2>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Plan <span className="font-semibold text-ink">{plan.nazwa}</span> — obciążymy{' '}
                <span className="font-semibold text-ink">{plan.netto} zł/mc</span> dopiero po 14 dniach.
                Anuluj wcześniej, nic nie pobierzemy.
              </p>
              <div className="mt-5 space-y-3">
                <label className="block text-xs font-semibold text-muted">Numer karty
                  <input value={karta.numer} onChange={(e) => setK('numer', e.target.value)} inputMode="numeric" autoComplete="cc-number" className={fld} placeholder="4242 4242 4242 4242" /></label>
                <div className="flex gap-3">
                  <label className="block flex-1 text-xs font-semibold text-muted">Ważność (MM/RR)
                    <input value={karta.exp} onChange={(e) => setK('exp', e.target.value)} inputMode="numeric" autoComplete="cc-exp" className={fld} placeholder="12/30" /></label>
                  <label className="block w-24 text-xs font-semibold text-muted">CVC
                    <input value={karta.cvc} onChange={(e) => setK('cvc', e.target.value)} inputMode="numeric" autoComplete="cc-csc" className={fld} placeholder="123" /></label>
                </div>
              </div>
              <p className="mt-3 flex items-center gap-1.5 text-[11px] text-muted">
                <Icon name="key" className="h-3 w-3 text-mint" /> Tryb testowy — użyj 4242 4242 4242 4242. Prawdziwe płatności po wpięciu bramki.
              </p>
              {blad && <p className="mt-3 text-xs font-medium text-danger">{blad}</p>}
              <button onClick={rozpocznijTrial} disabled={busy}
                className="mt-5 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60">
                {busy ? 'Chwila…' : 'Rozpocznij 14 dni za darmo →'}
              </button>
              <button onClick={() => setKrok('moduly')} className="mt-2 w-full text-center text-xs text-muted transition hover:text-ink">← Wróć</button>
            </div>
          </div>
        )}

        {/* Stawianie instancji */}
        {krok === 'stawianie' && (
          <div className="mx-auto max-w-md">
            <div className="card p-8 text-center">
              <span className="mx-auto grid h-12 w-12 animate-pulse place-items-center rounded-full bg-mint/15">
                <Icon name="office" className="h-6 w-6 text-mint" />
              </span>
              <h2 className="mt-4 font-display text-xl font-bold text-ink">Stawiamy Twój lokal…</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">Za chwilę przeniesiemy Cię do logowania.</p>
            </div>
          </div>
        )}

        <a href="?produkt" className="mt-8 block text-center text-xs text-muted transition hover:text-ink">← Wróć na stronę Lokalo</a>
      </div>
    </div>
  )
}
