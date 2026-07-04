import { useEffect, useState } from 'react'
import { api, setToken } from '../lib/api'
import { Logo } from '../components/Logo'
import { Spinner } from '../components/ui/Spinner'

// Publiczna strona rejestracji Z ZAPROSZENIA (?zaproszenie=TOKEN).
// Jedyna ścieżka założenia konta pracownika: manager generuje link w panelu
// (Konta → Zaproś pracownika), a osoba z linku ustala tylko login i hasło —
// konto od razu jest przypięte do właściwego pracownika i roli.
const fld = 'w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none transition focus:border-mint'

export default function Zaproszenie({ token }) {
  const [info, setInfo] = useState(null)      // dane zaproszenia (kogo, dokąd)
  const [blad, setBlad] = useState(null)      // błąd podglądu (wygasłe/użyte/nie istnieje)
  const [login, setLogin] = useState('')
  const [haslo, setHaslo] = useState('')
  const [haslo2, setHaslo2] = useState('')
  const [busy, setBusy] = useState(false)
  const [formBlad, setFormBlad] = useState(null)

  useEffect(() => {
    api(`/online/zaproszenie/${encodeURIComponent(token)}`)
      .then(setInfo)
      .catch((e) => setBlad(e.message))
  }, [token])

  const zarejestruj = async (e) => {
    e.preventDefault()
    setFormBlad(null)
    if (haslo !== haslo2) {
      setFormBlad('Hasła różnią się od siebie.')
      return
    }
    setBusy(true)
    try {
      const r = await api(`/online/zaproszenie/${encodeURIComponent(token)}/rejestracja`, 'POST', {
        login: login.trim(),
        haslo,
      })
      setToken(r.access_token)
      window.location.href = '/'   // pełne przeładowanie → App routuje wg roli konta
    } catch (err) {
      setFormBlad(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="relative min-h-dvh bg-bg text-ink">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-4 py-10 sm:px-6">
        <div className="mb-8 flex items-center gap-2.5">
          <Logo className="h-8" variant="gradient" />
          <span className="font-display text-lg font-bold">Lokalo</span>
        </div>

        {blad ? (
          <div className="card rounded-2xl p-6">
            <h1 className="font-display text-xl font-bold text-ink">Ten link nie działa</h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">{blad}</p>
            <p className="mt-4 text-sm text-muted">
              Poproś managera o nowe zaproszenie — link jest jednorazowy i ważny 7 dni.
            </p>
          </div>
        ) : !info ? (
          <div className="grid place-items-center py-16">
            <Spinner className="h-7 w-7 text-muted" />
          </div>
        ) : (
          <form onSubmit={zarejestruj} className="card rounded-2xl p-6">
            <h1 className="font-display text-2xl font-bold text-ink">
              Cześć, {info.imie}!
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              <span className="font-semibold text-ink">{info.nazwa_lokalu}</span> zaprasza Cię do
              swojej aplikacji. Ustal login i hasło — grafik, godziny i portfel będą czekać po
              pierwszym zalogowaniu.
            </p>

            <div className="mt-6 space-y-4">
              <div>
                <label className="field-label" htmlFor="zapr-login">Login</label>
                <input id="zapr-login" value={login} onChange={(e) => setLogin(e.target.value)}
                       className={fld} autoComplete="username" autoFocus />
                <span className="mt-1 block text-[11px] text-muted/80">min. 5 znaków, tylko litery i cyfry</span>
              </div>
              <div>
                <label className="field-label" htmlFor="zapr-haslo">Hasło</label>
                <input id="zapr-haslo" type="password" value={haslo} onChange={(e) => setHaslo(e.target.value)}
                       className={fld} autoComplete="new-password" />
                <span className="mt-1 block text-[11px] text-muted/80">min. 8 znaków, w tym cyfra i znak specjalny</span>
              </div>
              <div>
                <label className="field-label" htmlFor="zapr-haslo2">Powtórz hasło</label>
                <input id="zapr-haslo2" type="password" value={haslo2} onChange={(e) => setHaslo2(e.target.value)}
                       className={fld} autoComplete="new-password" />
              </div>
            </div>

            {formBlad && (
              <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{formBlad}</p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="mt-6 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60"
            >
              {busy ? 'Chwila…' : 'Załóż konto i wejdź'}
            </button>
            <p className="mt-3 text-center text-[11px] text-muted/70">
              Konto: {info.imie} {info.nazwisko} · rola: {info.rola}
            </p>
          </form>
        )}
      </div>
    </div>
  )
}
