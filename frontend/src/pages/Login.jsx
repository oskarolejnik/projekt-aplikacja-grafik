import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/ui/Toast'
import { Icon } from '../lib/icons'
import { Logo } from '../components/Logo'
import { Spinner } from '../components/ui/Spinner'

// Panel logowania (modal nad ekranem startowym). Po sukcesie AuthContext ustawia
// użytkownika, a App przełącza widok na panel admina lub samoobsługę pracownika.
export default function Login({ onClose }) {
  const { login } = useAuth()
  const { toast } = useToast()
  const [loginName, setLoginName] = useState('')
  const [haslo, setHaslo] = useState('')
  const [pokazHaslo, setPokazHaslo] = useState(false)
  const [busy, setBusy] = useState(false)
  const firstRef = useRef(null)

  // Autofokus na pole logowania — TYLKO przy otwarciu modala (pusta tablica).
  // Wcześniej zależność [onClose] powodowała ponowne ustawianie fokusu przy
  // każdym renderze rodzica (zegar tyka co sekundę → fokus „uciekał" do loginu).
  useEffect(() => {
    firstRef.current?.focus()
  }, [])

  // Zamknięcie klawiszem Escape.
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submit = async (e) => {
    e.preventDefault()
    if (!loginName.trim() || !haslo) {
      toast('Podaj login i hasło.', 'error')
      return
    }
    setBusy(true)
    try {
      await login(loginName.trim(), haslo)
      // sukces — komponent zniknie wraz z przełączeniem widoku w App
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1200] grid place-items-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label="Logowanie" className="card animate-fade-in relative z-10 w-full max-w-md p-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent-gradient">
            <Logo className="h-6" variant="bg" />
          </div>
          <div>
            <h2 className="font-display text-xl font-bold text-ink">Zaloguj się</h2>
            <p className="text-xs text-muted">Grafik Pracy — panel</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Login</span>
            <input
              ref={firstRef}
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              autoComplete="username"
              className="field"
              placeholder="np. jan.kowalski"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="field-label">Hasło</span>
            <div className="relative">
              <input
                type={pokazHaslo ? 'text' : 'password'}
                value={haslo}
                onChange={(e) => setHaslo(e.target.value)}
                autoComplete="current-password"
                className="field pr-11"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setPokazHaslo((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted transition hover:text-ink"
                aria-label={pokazHaslo ? 'Ukryj hasło' : 'Pokaż hasło'}
              >
                <Icon name={pokazHaslo ? 'close' : 'info'} className="h-4 w-4" />
              </button>
            </div>
          </label>

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cream px-6 py-3 text-sm font-bold uppercase tracking-[0.15em] text-bg shadow-cta transition hover:brightness-[1.03] active:scale-[0.98] disabled:opacity-60"
          >
            {busy ? <Spinner className="h-4 w-4" /> : <Icon name="logout" className="h-4 w-4 rotate-180" />}
            {busy ? 'Logowanie…' : 'Zaloguj się'}
          </button>
        </form>

        {onClose && (
          <button onClick={onClose} className="mt-4 w-full text-center text-xs text-muted transition hover:text-ink">
            Anuluj
          </button>
        )}
      </div>
    </div>
  )
}
