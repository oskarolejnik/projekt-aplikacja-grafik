import { useState, useEffect } from 'react'

// Baner cookies — serwis używa TYLKO pamięci niezbędnej do działania (np. sesja logowania),
// więc to informacja z potwierdzeniem, nie zgoda na śledzenie. Zapamiętuje wybór w localStorage.
const KLUCZ = 'lokalo_cookies_ok'

export default function BanerCookies() {
  const [widoczny, setWidoczny] = useState(false)

  useEffect(() => {
    try { setWidoczny(localStorage.getItem(KLUCZ) !== '1') } catch { setWidoczny(true) }
  }, [])

  const zamknij = () => {
    try { localStorage.setItem(KLUCZ, '1') } catch { /* prywatny tryb — pomiń */ }
    setWidoczny(false)
  }

  if (!widoczny) return null
  return (
    <div className="fixed inset-x-0 bottom-0 z-[60] px-3 pb-3">
      <div className="mx-auto flex w-full max-w-3xl flex-col items-start gap-3 rounded-xl border border-white/10 bg-black/80 px-4 py-3 text-xs text-muted backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
        <span className="leading-relaxed">
          Używamy plików cookie / pamięci przeglądarki wyłącznie w zakresie niezbędnym do działania serwisu
          (np. sesja logowania). Szczegóły w{' '}
          <a href="/?polityka" className="font-semibold text-mint hover:underline">Polityce prywatności</a>.
        </span>
        <button onClick={zamknij}
          className="shrink-0 rounded-lg bg-mint px-4 py-1.5 text-xs font-semibold text-bg transition hover:brightness-105 active:scale-[0.98]">
          Rozumiem
        </button>
      </div>
    </div>
  )
}
