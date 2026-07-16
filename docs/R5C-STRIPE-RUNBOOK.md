# R5c — uruchomienie i odbiór Stripe

Ten runbook zamyka wyłącznie bramę integracyjną R5c. Lokalny sandbox jest demonstracją i nie jest
dowodem gotowości produkcyjnej.

## 1. Konfiguracja test mode

Ustaw środowisko testowe jawnie:

```dotenv
APP_ENV=test
PAYMENTS_PROVIDER=stripe
STRIPE_RESTRICTED_KEY=rk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
PUBLIC_APP_URL=https://testowy-adres-lokalo.example
STRIPE_API_VERSION=2026-06-24.dahlia
STRIPE_EXPECTED_LIVEMODE=false
```

Restricted key powinien mieć tylko zakres potrzebny przez worker: zapis/odczyt Checkout Sessions,
PaymentIntents i Refunds oraz odczyt danych potrzebnych do kanonicznego uzgodnienia płatności.
Nie używaj publishable key ani szerokiego `sk_*`. Sekret webhooka pochodzi z konkretnego endpointu,
nie z panelu innego środowiska.

Endpoint webhooka:

```text
POST /api/online/platnosci/stripe/webhook
```

Subskrybuj zdarzenia obsługiwane przez R5c:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `payment_intent.amount_capturable_updated`
- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `payment_intent.canceled`
- `refund.created`
- `refund.updated`
- `refund.failed`

## 2. Scenariusz odbiorowy

1. Utwórz politykę zadatku PLN dla konkretnego dnia/serwisu i rezerwację publiczną.
2. Sprawdź, że aplikacja pokazuje oczekiwanie, a sam powrót z Checkout nie ustawia sukcesu.
3. Opłać Checkout w Stripe test mode i potwierdź przejście po podpisanym webhooku do `oplacona`.
4. Anuluj rezerwację, potwierdź polecenie pełnego zwrotu i webhook kończący stan `zwrocona`.
5. Powtórz webhook oraz żądanie anulowania — nie może powstać drugi zwrot.
6. Powtórz scenariusz preautoryzacji dla wizyty maksymalnie 6 dni naprzód: `autoryzowana`, następnie
   osobno pobranie i zwolnienie blokady.
7. Zasymuluj późny webhook sukcesu po anulowaniu; system ma automatycznie dopisać dokładnie jeden
   pełny zwrot.
8. Zasymuluj błąd/wygaśnięcie dla obu polityk `ponow` i `zwolnij`; retry ma tworzyć nową próbę, a
   `zwolnij` anulować rezerwację i oddać pojemność.

Opłata `no_show` jest zapisem księgowym operatora (`provider=ledger`), a nie pozorną transakcją
Stripe ani sandbox. Nie trafia do kolejki providera i jej ręczne rozliczenie nie zmienia pola zadatku
rezerwacji.

## 3. Monitoring i ręczne uzgodnienie

- Monitoruj komendy w stanach `retry`, `failed` i `uncertain` oraz webhooki, które wyczerpały retry.
- `uncertain` oznacza, że nie wolno tworzyć nowej operacji finansowej w ciemno. Użyj akcji
  „Sprawdź stan u operatora”: worker pobierze obiekt kanoniczny albo bezpiecznie wznowi pierwotne
  zlecenie z tym samym kluczem idempotencji, bez tworzenia drugiego obciążenia lub zwrotu.
- Jeśli niepewnych operacji jest kilka, jedno polecenie uzgodnienia przejdzie je automatycznie w
  kolejności zależności (`create_checkout` przed pobraniem, anulowaniem lub zwrotem). Panel pozostanie
  w stanie odświeżania do rozstrzygnięcia całego łańcucha.
- Panel operatora zachowuje ostatnią komendę, automatycznie odświeża stany przejściowe i blokuje
  konkurencyjną akcję. Dla `uncertain` zatrzymuje automatyczny polling do czasu jawnego uzgodnienia.
- Po uzgodnieniu sprawdź kwotę w minor units, walutę PLN, identyfikator obiektu, pojedynczy refund
  oraz to, że kolejki komend i webhooków wróciły do zera.

Każdy kanoniczny Checkout/PaymentIntent jest odrzucany, jeśli nie zgadza się referencja Lokalo,
waluta PLN lub pierwotna kwota. Refund jest dodatkowo wiązany z właściwym PaymentIntent, dzięki czemu
również pełny zwrot wykonany z Dashboardu Stripe może zostać poprawnie uzgodniony.

## 4. Dowód zamknięcia bramy

Zapisz bez sekretów:

- datę i środowisko testu,
- identyfikatory lokalnych płatności i zredagowane identyfikatory obiektów Stripe,
- stany komend oraz webhooków przed i po retry,
- potwierdzenie pojedynczego refundu,
- wynik testu uprawnień restricted key,
- wynik monitoringu pustej kolejki po zakończeniu scenariusza.

Dopiero ten dowód pozwala zmienić status roadmapy na `Done R5c`. Włączenie live wymaga osobnego,
kontrolowanego testu z `APP_ENV=production`, kluczem `rk_live_*`, sekretem live webhooka i
`STRIPE_EXPECTED_LIVEMODE=true`.

Kontrakt API: [Create a Checkout Session](https://docs.stripe.com/api/checkout/sessions/create) oraz
[Stripe-hosted Checkout](https://docs.stripe.com/payments/checkout).
