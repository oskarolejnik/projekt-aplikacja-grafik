import { useState } from 'react'
import { api, setToken } from '../lib/api'
import { useToast } from '../components/ui/Toast'
import { Logo } from '../components/Logo'

// Kreator pierwszej konfiguracji instancji (pojawia się tylko na pustej instancji — 0 użytkowników).
// Tworzy pierwszego administratora + nazwę lokalu przez publiczny POST /api/onboarding/bootstrap,
// po czym loguje (setToken) i przeładowuje do panelu admina.
const fld = 'w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none focus:border-mint'

export default function Onboarding() {
  const { toast } = useToast()
  const [form, setForm] = useState({ nazwa_lokalu: '', login: '', haslo: '' })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }))

  const zaloz = async () => {
    if (!form.nazwa_lokalu.trim()) { toast('Podaj nazwę lokalu.', 'error'); return }
    if (form.login.trim().length < 5) { toast('Login: min. 5 znaków (litery i cyfry).', 'error'); return }
    if (form.haslo.length < 8) { toast('Hasło: min. 8 znaków (litera + cyfra + znak specjalny).', 'error'); return }
    setBusy(true)
    try {
      const r = await api('/onboarding/bootstrap', 'POST', {
        login: form.login.trim(), haslo: form.haslo, nazwa_lokalu: form.nazwa_lokalu.trim(),
      })
      setToken(r.access_token)
      toast('Instancja skonfigurowana — zaloguję Cię…', 'success')
      window.location.href = '/'   // przeładuj → AuthProvider podłapie token i pokaże panel admina
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  return (
    <div className="relative min-h-dvh bg-bg px-4 py-10">
      <div aria-hidden className="pointer-events-none fixed -left-40 -top-40 h-[28rem] w-[28rem] rounded-full bg-page-glow opacity-[0.12] blur-2xl" />
      <div className="relative z-10 mx-auto flex min-h-[80dvh] w-full max-w-md flex-col justify-center">
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-9" variant="gradient" />
          <div>
            <h1 className="font-display text-xl font-bold text-ink">Pierwsza konfiguracja</h1>
            <p className="text-xs text-muted">Utwórz konto administratora i nazwij swój lokal.</p>
          </div>
        </div>

        <div className="card p-6 sm:p-8">
          <div className="space-y-3">
            <label className="block text-xs font-semibold text-muted">Nazwa lokalu
              <input value={form.nazwa_lokalu} onChange={(e) => set('nazwa_lokalu', e.target.value)} className={fld} placeholder="Moja Restauracja" /></label>
            <label className="block text-xs font-semibold text-muted">Login administratora
              <input value={form.login} onChange={(e) => set('login', e.target.value)} className={fld} placeholder="min. 5 znaków, litery i cyfry" /></label>
            <label className="block text-xs font-semibold text-muted">Hasło
              <input type="password" value={form.haslo} onChange={(e) => set('haslo', e.target.value)} className={fld} placeholder="min. 8 znaków: litera + cyfra + znak specjalny" /></label>
          </div>
          <button onClick={zaloz} disabled={busy}
            className="mt-5 w-full rounded-xl bg-accent-gradient px-4 py-3 text-sm font-bold text-bg shadow-cta transition hover:brightness-105 disabled:opacity-60">
            {busy ? 'Zakładam…' : 'Utwórz i rozpocznij'}
          </button>
          <p className="mt-3 text-center text-xs text-muted/70">Ten kreator pojawia się tylko na nowej, pustej instancji.</p>
        </div>
      </div>
    </div>
  )
}
