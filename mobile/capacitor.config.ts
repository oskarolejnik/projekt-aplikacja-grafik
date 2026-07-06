import type { CapacitorConfig } from '@capacitor/cli';

// Powłoka natywna „Lokalo" (Capacitor). Pakuje ZBUDOWANY frontend (../frontend/dist)
// do aplikacji iOS/Android. Aplikacja łączy się z instancją lokalu po adresie podanym
// na ekranie „Podłącz lokal" (WyborInstancji.jsx) — dlatego jeden build obsługuje wszystkie lokale.
const config: CapacitorConfig = {
  appId: 'pl.lokalo.app',
  appName: 'Lokalo',
  webDir: '../frontend/dist',
  android: {
    // WebView serwuje spod https://localhost (bezpieczny kontekst: Web Crypto, PWA, secure cookies).
    // Ten origin jest dozwolony w CORS backendu — patrz settings.NATIVE_ORIGINS.
  },
  ios: {
    // WebView serwuje spod capacitor://localhost (również dozwolone w settings.NATIVE_ORIGINS).
    // Realny build iOS wymaga macOS + Xcode (Faza 6).
  },
  plugins: {
    PushNotifications: {
      // Powiadomienia natywne: Android → FCM, iOS → APNs (pośrednio przez FCM).
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

export default config;
