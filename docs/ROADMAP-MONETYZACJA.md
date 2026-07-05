# Roadmapa monetyzacji Lokalo — płatności, KSeF, aplikacje mobilne

*Research + weryfikacja faktów: lipiec 2026. Dokument prowadzi wdrożenie płatności za
subskrypcje, fakturowania (KSeF) i aplikacji mobilnych. Każda faza mówi wprost: co da się
zbudować w kodzie bez żadnych zewnętrznych kont, a co wymaga kont/kluczy/decyzji operatora.*

## Zweryfikowane fakty (na których stoi plan)

| Temat | Werdykt | Konsekwencja |
|---|---|---|
| **Apple IAP** | Nie jest bezwzględnie wymagany, ale **tylko model „login-only / companion"** (aplikacja darmowa, zero cennika/zakupu/CTA w apce, subskrypcja kupowana na webie) — wytyczna 3.1.3(b). NIE opierać się na „enterprise 3.1.3(c)". Realne ryzyko odrzucenia pod 3.1.1 → demo-konto dla recenzenta + odwołanie. | Sprzedaż subskrypcji zostaje w panelu web; apka iOS tylko loguje. |
| **Google Play Billing** | Od **4.03.2026** globalna liberalizacja — Play Billing **przestał być obowiązkowy**; w EOG (Polska) do **30.06.2026** wolno kierować na web-checkout. Model „consumption-only" (login-only) i tak najbezpieczniejszy = **0% prowizji**. | Kanał Android odblokowany bez prowizji 15–30%. |
| **KSeF** | Obowiązek wystawiania dla zwykłego podatnika VAT: **01.04.2026** (duzi: 01.02.2026). Odbieranie e-faktur dla wszystkich od 01.02.2026. Schemat **FA(3)** (nie FA(2)). **Środowisko testowe API istnieje**: `https://ksef-test.mf.gov.pl/` — development bez niczego firmowego. | Kod generatora FA(3) buduję teraz na teście; certyfikat prod dopiero przed 04.2026. |
| **Bramka płatnicza** | 🥇 **Stripe Billing** (recurring BLIK+P24, webhooki mapują się 1:1 na degradację READ_ONLY, ~1,5–1,6%). 🥈 P24/Autopay (polski fallback BLIK-first). ❌ Merchant-of-Record (Paddle/Lemon Squeezy) — wystawia fakturę na SWÓJ NIP, psuje polskie B2B/KSeF. | Driver `stripe` za tą samą abstrakcją co sandbox; fakturę i tak wystawiamy sami (KSeF). |

## Fazy (kolejność wg ryzyka i zależności)

### Faza 0 — Fundament rozliczeniowy · *zero kont*
Model danych + logika w sandboxie, żeby reszta tylko podmieniała driver na prawdziwy.
- `cennik.py`: ceny netto per tier (Basic 99 / Pro 199 / Premium 349), poziomy, stawka VAT 23%.
- Migracja: `Subskrypcja` + `cena_netto`, `saldo_kredytu`; nowe tabele `PlatnoscSubskrypcji`
  (rozbicie VAT) i `HistoriaSubskrypcji` (audyt zmian tieru).
- Rozszerzenie abstrakcji płatności (`provider=sandbox` → link + „oznacz opłaconą").

### Faza 1 — Egzekwowanie READ_ONLY · *zero kont* · **najwyższa dźwignia**
Aplikacja realnie blokuje lokal, który nie zapłacił.
- `data_do` = koniec opłaconego okresu; `data_grace = data_do + 7 dni`.
- Do `data_grace`: **miękka degradacja** (baner „faktura po terminie"), pełny dostęp.
  Po `data_grace`: **twarde READ_ONLY** — wszystkie zapisy → HTTP 402 (mechanizm już jest,
  dokładamy grace + stany).
- Allowlista spod blokady: `/api/auth/*`, `/api/subskrypcja/*` (żeby dało się zapłacić z READ_ONLY),
  webhook płatności.
- Przypomnienia (scheduler): mail/push T-3, T-0, T+3 względem `data_do`.

### Faza 2 — Upgrade z dopłatą (proration) · *zero kont*
Zmiana planu w środku okresu = **dopłata tylko za różnicę** za pozostałe dni.
```
współczynnik  = pozostałe_dni / dni_w_okresie
dopłata_netto = round((nowa_cena − stara_cena) × współczynnik, 2)
```
Przykład Pro→Premium 16.07 (okres 01–31.07): `(349−199)×15/30 = 75,00 zł netto` + VAT = 92,25 zł
brutto; tier w górę od razu, pełne 349 od następnego okresu. Downgrade = kredyt na następny okres.
- `subskrypcja_billing.oblicz_prorate()` (czysta funkcja), `GET /api/subskrypcja/upgrade/podglad`,
  `POST /api/subskrypcja/upgrade` (w allowliście 402).

### Faza 3 — Fakturowanie + generator FA(3) · *kod: zero kont; prod: certyfikat*
Po każdej płatności powstaje polska faktura VAT z NIP klienta, gotowa do KSeF.
- Model faktury (numeracja `LOK/2026/07/0042`, `ksef_number`, `upo_xml`, `status_ksef`).
- Generator XML **FA(3)**: sprzedawca = operator, nabywca = NIP lokalu, okres abonamentu,
  rozbicie netto/VAT/brutto; upgrade = osobna faktura na dopłatę.
- `ksef_driver.py` (test → demo → prod) — walidacja przeciw `ksef-test.mf.gov.pl` certyfikatem testowym.
- **Wymaga operatora (przed 04.2026, nie teraz):** forma prawna (sp. z o.o. → pieczęć kwalifikowana
  na NIP, idealna dla automatu; JDG → podpis/Profil Zaufany) + wygenerowanie certyfikatu KSeF.

### Faza 4 — Integracja bramki (Stripe) · *wymaga konta*
Prawdziwe cykliczne obciążanie karty/BLIK.
- Przepływ: rejestracja karty (SetupIntent) → subskrypcja cykliczna → webhook `invoice.paid`
  → `PlatnoscSubskrypcji.oplacona` + przesuń `data_do` +miesiąc; `payment_failed`/`subscription.deleted`
  → grace/READ_ONLY z Fazy 1.
- Driver `provider=stripe` za tą samą abstrakcją; webhook idempotentny + weryfikacja podpisu.
  Testowalny **kluczami testowymi Stripe** (konto testowe bez umowy).
- **Wymaga operatora:** konto Stripe (KYC), klucze prod, ew. P24/Autopay jako fallback, most fakturowy.

### Faza 5 — Android (Capacitor, consumption-only) · *build na Windows; publikacja wymaga konta*
Apka Android w Google Play, 0% prowizji.
- Capacitor init (`pl.lokalo.app`), bundlowanie `dist` + ekran „adres instancji".
- **Obowiązkowa zmiana web:** `api.js` z hardkodowanego `/api` na konfigurowalny base URL
  (bez tego apka nie trafi w serwer klienta). To robimy już w Fazie 0/5-web.
- FCM push (obok istniejącego web-push VAPID), endpoint rejestracji tokenu natywnego.
- **Wymaga operatora:** Google Play Developer **25 USD** jednorazowo, konto Organization + **D-U-N-S**
  (darmowy, ~tydzień — zamów wcześnie), Firebase (`google-services.json`), Data safety + polityka
  prywatności. Cały build AAB robi się na Windows.

### Faza 6 — iOS (Capacitor, login-only) · *build/podpis wymaga macOS*
Apka iOS w App Store bez IAP.
- Kod React + `npx cap add ios` piszę na Windows; **build/podpis/wysyłka wyłącznie na macOS**
  (własny Mac / mac w chmurze / **CI GitHub Actions `macos-latest`** — rekomendacja).
- **Wymaga operatora:** Apple Developer **99 USD/rok**, Organization + D-U-N-S, Xcode 26+
  (deadline narzędziowy 28.04.2026), App Privacy labels, ścieżka usunięcia konta.
- Kolejność ostatnia — najdroższa i zależy od maca; Android daje ~80% wartości mobile wcześniej.

### Faza 7 — Hardening i produkcja
Przełączenie wszystkiego test→prod (Stripe, certyfikat KSeF, Firebase, Apple/Google), monitoring,
E2E na realnej płatności.

## NAJPIERW — buduję od zaraz (zero kont zewnętrznych)
1. `cennik.py` + migracja (ceny, `PlatnoscSubskrypcji`, `HistoriaSubskrypcji`).
2. Egzekwowanie READ_ONLY z grace period (Faza 1) — **najwyższa dźwignia**.
3. `subskrypcja_billing.py` + endpointy proration/upgrade (Faza 2).
4. Generator FA(3) + `ksef_driver.py` na środowisko testowe (Faza 3, kod).
5. Refaktor `api.js` na konfigurowalny base URL + Capacitor init (Faza 5-web) — odblokowuje Androida.

## Decyzje operatora poza kodem (mają lead time — zacznij równolegle)
- **Forma prawna firmy** (sp. z o.o. vs JDG) — determinuje typ pieczęci/podpisu KSeF.
- **Wniosek o numer D-U-N-S** (darmowy, ~tydzień) — potrzebny i dla Apple, i dla Google.
- Założenie konta **Stripe** (KYC kilka dni) — gdy dojdziemy do Fazy 4.
