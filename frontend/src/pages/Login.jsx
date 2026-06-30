import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { useBranding } from '../context/BrandingContext'
import { useToast } from '../components/ui/Toast'
import { Icon } from '../lib/icons'
import { Logo } from '../components/Logo'
import { Spinner } from '../components/ui/Spinner'
import { motion } from 'framer-motion'

// Walidacja po stronie klienta (natychmiastowy feedback). Serwer waliduje ponownie
// — to ta sama logika, ale front daje od razu czytelny komunikat.
function walidujRejestracje({ login, haslo, imie, nazwisko }) {
  if (!imie.trim() || !nazwisko.trim()) return 'Podaj imię i nazwisko.'
  if (login.trim().length < 5) return 'Login musi mieć co najmniej 5 znaków.'
  if (!/^[A-Za-z0-9]+$/.test(login.trim())) return 'Login: tylko litery i cyfry (bez spacji i polskich znaków).'
  if (haslo.length < 8) return 'Hasło musi mieć co najmniej 8 znaków.'
  if (/[^\x21-\x7e]/.test(haslo)) return 'Hasło: tylko znaki ASCII (bez spacji i polskich liter).'
  if (!/[A-Za-z]/.test(haslo)) return 'Hasło musi zawierać literę.'
  if (!/\d/.test(haslo)) return 'Hasło musi zawierać cyfrę.'
  if (!/[^A-Za-z0-9]/.test(haslo)) return 'Hasło musi zawierać znak specjalny (np. ! @ # $).'
  return null
}

export default function Login({ onClose }) {
  const { login, register } = useAuth()
  const { nazwa_lokalu } = useBranding()
  const { toast } = useToast()
  const [tryb, setTryb] = useState('login') // 'login' | 'register'
  const [loginName, setLoginName] = useState(() => localStorage.getItem('grafik_login') || '')
  const [haslo, setHaslo] = useState('')
  const [imie, setImie] = useState('')
  const [nazwisko, setNazwisko] = useState('')
  const [pokazHaslo, setPokazHaslo] = useState(false)
  const [zapamietaj, setZapamietaj] = useState(true)
  const [busy, setBusy] = useState(false)
  const formRef = useRef(null)

  const rejestracja = tryb === 'register'

  // Fokus na pierwszym polu — przy otwarciu i po zmianie trybu (login/rejestracja).
  useEffect(() => {
    formRef.current?.querySelector('input')?.focus()
  }, [tryb])

  // Zamknięcie klawiszem Escape.
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      if (rejestracja) {
        const blad = walidujRejestracje({ login: loginName, haslo, imie, nazwisko })
        if (blad) {
          toast(blad, 'error')
          return
        }
        await register({ login: loginName.trim(), haslo, imie: imie.trim(), nazwisko: nazwisko.trim() })
      } else {
        if (!loginName.trim() || !haslo) {
          toast('Podaj login i hasło.', 'error')
          return
        }
        await login(loginName.trim(), haslo, zapamietaj)
        if (zapamietaj) localStorage.setItem('grafik_login', loginName.trim())
        else localStorage.removeItem('grafik_login')
      }
      // sukces — komponent zniknie wraz z przełączeniem widoku w App
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[1200] grid place-items-center p-4">
      <motion.div
        className="absolute inset-0 bg-black/70 backdrop-blur-md"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3, ease: 'circOut' }}
      />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label={rejestracja ? 'Rejestracja' : 'Logowanie'}
        className="card relative z-10 w-full max-w-md p-8"
        initial={{ opacity: 0, scale: 0.98, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 10 }}
        transition={{ duration: 0.32, ease: 'circOut' }}
      >
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-9" variant="gradient" />
          <div>
            <h2 className="font-display text-xl font-bold text-ink">{rejestracja ? 'Zarejestruj się' : 'Zaloguj się'}</h2>
            <p className="text-xs text-muted">{rejestracja ? 'Załóż konto pracownika' : `${nazwa_lokalu} — panel`}</p>
          </div>
        </div>

        <form ref={formRef} onSubmit={submit} className="space-y-4">
          {rejestracja && (
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Imię</span>
                <input value={imie} onChange={(e) => setImie(e.target.value)} autoComplete="given-name" className="field" placeholder="Jan" />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="field-label">Nazwisko</span>
                <input value={nazwisko} onChange={(e) => setNazwisko(e.target.value)} autoComplete="family-name" className="field" placeholder="Kowalski" />
              </label>
            </div>
          )}

          <label className="flex flex-col gap-1.5">
            <span className="field-label">Login</span>
            <input
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              autoComplete="username"
              className="field"
              placeholder="np. jankowalski"
            />
            {rejestracja && <span className="text-[11px] text-muted/80">min. 5 znaków, tylko litery i cyfry</span>}
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="field-label">Hasło</span>
            <div className="relative">
              <input
                type={pokazHaslo ? 'text' : 'password'}
                value={haslo}
                onChange={(e) => setHaslo(e.target.value)}
                autoComplete={rejestracja ? 'new-password' : 'current-password'}
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
            {rejestracja && <span className="text-[11px] text-muted/80">min. 8 znaków, w tym cyfra i znak specjalny</span>}
          </label>

          {!rejestracja && (
            <label className="-mt-1 flex cursor-pointer select-none items-center gap-2.5 text-sm text-muted">
              <input
                type="checkbox"
                checked={zapamietaj}
                onChange={(e) => setZapamietaj(e.target.checked)}
                className="h-4 w-4 rounded border-line bg-transparent accent-cream"
              />
              Zapamiętaj mnie na tym urządzeniu
            </label>
          )}

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cream px-6 py-3 text-sm font-bold uppercase tracking-[0.15em] text-bg shadow-cta transition hover:brightness-[1.03] active:scale-[0.98] disabled:opacity-60"
          >
            {busy ? <Spinner className="h-4 w-4" /> : <Icon name="logout" className="h-4 w-4 rotate-180" />}
            {busy ? 'Chwila…' : rejestracja ? 'Zarejestruj się' : 'Zaloguj się'}
          </button>
        </form>

        <div className="mt-5 text-center text-xs text-muted">
          {rejestracja ? (
            <>
              Masz już konto?{' '}
              <button onClick={() => setTryb('login')} className="font-semibold text-ink underline-offset-2 hover:underline">
                Zaloguj się
              </button>
            </>
          ) : (
            <>
              Nie masz konta?{' '}
              <button onClick={() => setTryb('register')} className="font-semibold text-ink underline-offset-2 hover:underline">
                Zarejestruj się
              </button>
            </>
          )}
        </div>

        {onClose && (
          <button onClick={onClose} className="mt-3 w-full text-center text-xs text-muted transition hover:text-ink">
            Anuluj
          </button>
        )}
      </motion.div>
    </div>
  )
}
