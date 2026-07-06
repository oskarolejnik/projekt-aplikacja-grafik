# Aplikacja mobilna Lokalo (iOS + Android)

Powłoka natywna oparta o **Capacitor**. Pakuje ten sam frontend co wersja web
(`frontend/dist`) do aplikacji na sklepy Apple App Store i Google Play. Jeden build
obsługuje **wszystkie lokale** — po instalacji użytkownik podaje adres swojej instancji
na ekranie „Podłącz lokal" (`frontend/src/pages/WyborInstancji.jsx`), a aplikacja od tego
momentu rozmawia z tym backendem (patrz `frontend/src/lib/api.js` → `getApiBase/setApiBase`).

Cała konfiguracja Capacitora leży w katalogu **`mobile/`**, celowo odseparowana od
`frontend/` — dzięki temu web-build i jego lockfile (a więc i CI) są nietknięte przez
zależności natywne.

---

## Architektura powłoki

| Warstwa | Co robi |
|---|---|
| `frontend/` | Kod React/Vite. `npm run build` → `frontend/dist`. Ten sam kod na web i mobile. |
| `mobile/capacitor.config.ts` | `webDir: '../frontend/dist'`, `appId: pl.lokalo.app`, plugin push. |
| `mobile/android/`, `mobile/ios/` | Projekty natywne generowane przez `npx cap add …` (nie w repo — regenerowalne). |
| Ekran „Podłącz lokal" | Pokazywany tylko w apce natywnej, gdy brak zapisanego adresu instancji. |
| Powiadomienia | Web → Web Push/VAPID. Natywne → FCM (Android) / APNs (iOS), token: `POST /api/me/push/register-native`. |

**Wykrywanie platformy:** `frontend/src/lib/platforma.js` → `jestNatywna()` sprawdza
`window.Capacitor.isNativePlatform()`. Na web zwraca `false` i cała logika natywna jest
pomijana (adres API = pusty → względne `/api`, identycznie jak dziś).

---

## Wymagania wstępne (wspólne)

- Node.js 20+ i npm.
- Konto **Firebase** (dla powiadomień push — Android FCM, iOS APNs przez FCM). Darmowy plan wystarcza.

---

## Android (buduje się na Windows / Linux / macOS)

### Jednorazowa konfiguracja

1. **Android Studio** + Android SDK (API 34+), zmienna `JAVA_HOME` (JDK 17).
2. Instalacja zależności i dodanie platformy:
   ```bash
   cd mobile
   npm install
   npm run build:web        # buduje ../frontend/dist
   npx cap add android      # generuje mobile/android/
   ```
3. **Firebase / FCM:**
   - W konsoli Firebase dodaj aplikację Android o `applicationId = pl.lokalo.app`.
   - Pobierz `google-services.json` i wrzuć do `mobile/android/app/` (plik jest w `.gitignore`).
   - Dodaj plugin Google Services zgodnie z instrukcją `@capacitor/push-notifications`
     (wpis w `android/build.gradle` i `android/app/build.gradle`).
4. Ikona i splash: podmień zasoby w `mobile/android/app/src/main/res/` (lub użyj `@capacitor/assets`).

### Build do testów i na sklep

```bash
cd mobile
npm run android:sync       # build web + cap sync android
npm run android:open       # otwiera Android Studio
```

- **APK testowy:** w Android Studio *Build → Build APK(s)*.
- **AAB na Google Play** (wymagany format): *Build → Generate Signed Bundle/APK → Android App Bundle*.
  - Wygeneruj **keystore** (upload key) i przechowuj bezpiecznie — bez niego nie zaktualizujesz aplikacji.
  - Włącz **Play App Signing** przy pierwszym wydaniu.

### Google Play — czego wymaga sklep

- Konto **Google Play Developer** — jednorazowa opłata **25 USD**.
- Weryfikacja tożsamości wydawcy (D-U-N-S dla firmy albo dane osobowe).
- Karta produktu: ikona 512×512, grafika główna 1024×500, min. 2 zrzuty ekranu, opis PL.
- **Polityka prywatności** (URL) i wypełniony formularz *Data safety* (jakie dane zbieracie).
- Docelowy `targetSdkVersion` zgodny z bieżącym wymogiem Play (aktualizowany co roku).
- Deklaracja uprawnień (m.in. `POST_NOTIFICATIONS` na Androidzie 13+).

---

## iOS (wymaga macOS + Xcode) — Faza 6

Kod jest gotowy (origin `capacitor://localhost` dozwolony w CORS, plugin push wspiera APNs),
ale **build i wysyłka wymagają macOS** — nie da się tego zrobić na Windows.

### Konfiguracja (na macOS)

```bash
cd mobile
npm install
npm run build:web
npx cap add ios
npm run ios:open           # otwiera Xcode
```

- Plik `GoogleService-Info.plist` z Firebase → do projektu iOS.
- Włącz zdolność **Push Notifications** i **Background Modes → Remote notifications** w Xcode.
- Klucz **APNs** (.p8) wgraj do Firebase, aby FCM dostarczał powiadomienia na iOS.

### Apple App Store — czego wymaga sklep

- **Apple Developer Program** — subskrypcja **99 USD/rok**.
- Certyfikaty i profile provisioning (zarządzane przez Xcode / App Store Connect).
- Karta w App Store Connect: ikona 1024×1024, zrzuty ekranu dla wymaganych rozmiarów, opis PL.
- **App Privacy** („Privacy Nutrition Labels") + URL polityki prywatności.
- Zgodność z App Review Guidelines (m.in. logowanie testowe dla recenzenta, brak treści niedozwolonych).
- Bez własnego Maca: build iOS przez CI z macOS runnerem (np. GitHub Actions `macos-latest`, Codemagic, Bitrise).

---

## Powiadomienia natywne — jak działają

1. Po zalogowaniu `frontend/src/components/PushButton.jsx` wykrywa apkę natywną i woła
   `zarejestrujPushNatywny()` (`frontend/src/lib/pushNative.js`).
2. Plugin `@capacitor/push-notifications` prosi o zgodę i zwraca token urządzenia (FCM/APNs).
3. Token trafia do backendu: `POST /api/me/push/register-native` → tabela `push_device_tokens`.
4. Wysyłka: `backend/push.py` → `_wyslij_fcm(...)`. **Realna wysyłka przez FCM HTTP v1 jest
   podpięta warunkowo** — wymaga konta serwisowego Firebase operatora (zmienne `FCM_PROJECT_ID`
   / `FCM_SERVICE_ACCOUNT`). Bez nich kanał natywny jest pomijany (log), a web push działa normalnie.

> **TODO produkcyjne (Faza 5 prod):** dopięcie realnego POST-a do
> `https://fcm.googleapis.com/v1/projects/<PROJECT>/messages:send` (OAuth z konta serwisowego)
> oraz kasowanie tokenów na `UNREGISTERED`. Miejsce w kodzie oznaczone `TODO(Faza 5 prod)`.

---

## Aktualizacje aplikacji

- **Zmiany w warstwie web** (React) nie wymagają nowego wydania w sklepie: wystarczy wdrożyć
  nowy `frontend/dist` na instancji — apka pobiera świeży frontend przy połączeniu.
  (Uwaga: przy pierwszym uruchomieniu apka ładuje web z bundla; docelowo warto rozważyć
  `@capacitor/live-updates` lub ładowanie web zdalnie z instancji.)
- **Zmiany natywne** (pluginy, uprawnienia, ikony) wymagają nowego buildu i wydania w sklepie.
