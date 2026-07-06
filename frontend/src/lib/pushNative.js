import { api } from './api'
import { jestNatywna } from './platforma'

// Powiadomienia NATYWNE (Capacitor: FCM na Androidzie, APNs na iOS).
// Web Push/VAPID nie działa w apce natywnej — token urządzenia bierzemy z pluginu
// @capacitor/push-notifications i rejestrujemy w backendzie (POST /me/push/register-native).
//
// Celowo NIE importujemy pluginu statycznie (import '@capacitor/push-notifications'),
// żeby build webowy nie wymagał tej zależności. Sięgamy do runtime'u przez
// window.Capacitor.Plugins.PushNotifications — plugin jest wstrzykiwany tylko w apce natywnej.

function pluginPush() {
  return (typeof window !== 'undefined' && window.Capacitor && window.Capacitor.Plugins)
    ? window.Capacitor.Plugins.PushNotifications
    : null
}

function platforma() {
  try {
    return (window.Capacitor.getPlatform && window.Capacitor.getPlatform()) || null
  } catch (_) {
    return null
  }
}

// Rejestruje urządzenie do powiadomień natywnych. No-op poza apką natywną
// (na webie push idzie kanałem Web Push — patrz lib/push.js).
// Best-effort: błędy łykamy, żeby nie wywracać startu aplikacji.
export async function zarejestrujPushNatywny() {
  if (!jestNatywna()) return false
  const Push = pluginPush()
  if (!Push) return false
  try {
    let perm = await Push.checkPermissions()
    if (perm.receive !== 'granted') {
      perm = await Push.requestPermissions()
    }
    if (perm.receive !== 'granted') return false

    // Token przychodzi asynchronicznie zdarzeniem 'registration' — nasłuchujemy raz,
    // potem wołamy register(), który to zdarzenie wyzwala.
    const token = await new Promise((resolve, reject) => {
      let zalatwione = false
      Push.addListener('registration', (t) => {
        if (zalatwione) return
        zalatwione = true
        resolve(t && t.value)
      })
      Push.addListener('registrationError', (e) => {
        if (zalatwione) return
        zalatwione = true
        reject(new Error(e && e.error ? e.error : 'registrationError'))
      })
      Push.register()
    })

    if (!token) return false
    await api('/me/push/register-native', 'POST', { token, platform: platforma() })
    return true
  } catch (_) {
    return false
  }
}
