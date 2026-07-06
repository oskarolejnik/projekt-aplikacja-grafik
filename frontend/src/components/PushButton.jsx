import { useEffect, useState } from 'react'
import { Icon } from '../lib/icons'
import { useToast } from './ui/Toast'
import { pushWspierany, wlaczPowiadomienia, odswiezSubskrypcje } from '../lib/push'
import { jestNatywna } from '../lib/platforma'
import { zarejestrujPushNatywny } from '../lib/pushNative'

// Wspólny przycisk powiadomień push — dla KAŻDEGO panelu (pracownik, kuchnia, admin,
// szef, szef kuchni). Subskrypcja jest zapisywana per użytkownik (user_id), więc działa
// też dla kont bez powiązanego pracownika (admin/szef).
//
// • Web: Web Push (VAPID). Apka natywna (Capacitor): token FCM/APNs (lib/pushNative.js).
// • PODŚWIETLONY (mint) gdy powiadomienia są włączone — czytelny status na pierwszy rzut oka.
// • Klik włącza/odświeża subskrypcję (best-effort „heal" — subskrypcje potrafią cicho wygasać).
export function PushButton({ className = '' }) {
  const { toast } = useToast()
  const [pushOn, setPushOn] = useState(false)

  // Przy wejściu odśwież/zarejestruj powiadomienia (gdy zgoda już udzielona) i ustaw stan.
  useEffect(() => {
    if (jestNatywna()) {
      zarejestrujPushNatywny().then((ok) => { if (ok) setPushOn(true) })
    } else {
      odswiezSubskrypcje().then((ok) => { if (ok) setPushOn(true) })
    }
  }, [])

  if (!jestNatywna() && !pushWspierany()) return null

  const klik = async () => {
    const bylWlaczony = pushOn
    try {
      if (jestNatywna()) {
        const ok = await zarejestrujPushNatywny()
        if (!ok) throw new Error('Nie udało się włączyć powiadomień (sprawdź uprawnienia w ustawieniach systemu).')
      } else {
        await wlaczPowiadomienia()
      }
      setPushOn(true)
      toast(bylWlaczony ? 'Powiadomienia są włączone.' : 'Powiadomienia włączone.', 'success')
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  return (
    <button
      onClick={klik}
      aria-pressed={pushOn}
      title={pushOn ? 'Powiadomienia włączone' : 'Włącz powiadomienia'}
      className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition ${
        pushOn
          ? 'border-mint/50 bg-mint/15 text-mint ring-1 ring-inset ring-mint/20'
          : 'border-line bg-white/[0.04] text-muted hover:text-ink'
      } ${className}`}
    >
      <Icon name="bell" className="h-4 w-4" />
      <span className="hidden md:inline">{pushOn ? 'Powiadomienia włączone' : 'Powiadomienia'}</span>
    </button>
  )
}
