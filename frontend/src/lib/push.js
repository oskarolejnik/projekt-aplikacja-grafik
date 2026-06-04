import { api } from './api'

// VAPID public key (base64url) -> Uint8Array dla pushManager.subscribe.
function base64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b)
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

// Czy przeglądarka w ogóle wspiera push (i jesteśmy w bezpiecznym kontekście).
export function pushWspierany() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

// Prosi o zgodę, subskrybuje push i wysyła subskrypcję do backendu.
export async function wlaczPowiadomienia() {
  if (!pushWspierany()) {
    throw new Error('Powiadomienia push nie są wspierane na tym urządzeniu/przeglądarce.')
  }
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') throw new Error('Brak zgody na powiadomienia.')

  const { publicKey } = await api('/me/push/public-key')
  if (!publicKey) throw new Error('Powiadomienia nie są skonfigurowane na serwerze (brak kluczy VAPID).')

  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64ToUint8Array(publicKey),
  })
  await api('/me/push/subscribe', 'POST', sub.toJSON())
  return true
}
