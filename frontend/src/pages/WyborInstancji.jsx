import { useState } from 'react'
import { setApiBase, sprawdzInstancje } from '../lib/api'
import { Logo } from '../components/Logo'
import { Spinner } from '../components/ui/Spinner'

// Ekran pierwszego uruchomienia aplikacji NATYWNEJ (Capacitor): treść jest bundlowana lokalnie,
// więc apka musi wiedzieć, pod jakim adresem stoi instancja lokalu. Użytkownik podaje adres
// (np. mojlokal.lokalo.pl); po sprawdzeniu /api/health zapisujemy go i przeładowujemy do panelu.
// Na webie ten ekran nigdy się nie pokazuje (baza API jest względna).
export default function WyborInstancji({ onGotowe }) {
  const [adres, setAdres] = useState('https://')
  const [busy, setBusy] = useState(false)
  const [blad, setBlad] = useState(null)

  const polacz = async () => {
    let url = adres.trim()
    if (!url) { setBlad('Podaj adres swojego Lokalo.'); return }
    if (!/^https?:\/\//i.test(url)) url = 'https://' + url
    setBusy(true); setBlad(null)
    const ok = await sprawdzInstancje(url)
    setBusy(false)
    if (!ok) { setBlad('Nie znaleziono Lokalo pod tym adresem. Sprawdź pisownię i połączenie.'); return }
    setApiBase(url)
    if (onGotowe) onGotowe()
    else window.location.reload()
  }

  return (
    <div className="relative min-h-dvh bg-bg text-ink">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-6 py-10">
        <div className="mb-8 flex items-center gap-2.5">
          <Logo className="h-9" variant="gradient" />
          <span className="font-display text-lg font-bold">Lokalo</span>
        </div>
        <h1 className="font-display text-2xl font-bold" style={{ textWrap: 'balance' }}>Połącz z Twoim lokalem</h1>
        <p className="mt-2 text-sm text-muted">
          Podaj adres swojego Lokalo — znajdziesz go w panelu albo w mailu powitalnym
          (np. <span className="text-ink">mojlokal.lokalo.pl</span>). Zapamiętamy go na tym urządzeniu.
        </p>
        <input
          value={adres}
          onChange={(e) => setAdres(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') polacz() }}
          autoCapitalize="none" autoCorrect="off" inputMode="url"
          className="mt-6 w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none focus:border-mint"
          placeholder="https://mojlokal.lokalo.pl"
        />
        {blad && <p className="mt-2 text-sm font-medium text-danger">{blad}</p>}
        <button
          onClick={polacz}
          disabled={busy}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-60"
        >
          {busy ? <Spinner className="h-4 w-4" /> : null}
          {busy ? 'Sprawdzam…' : 'Połącz'}
        </button>
      </div>
    </div>
  )
}
